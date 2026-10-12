"""Election data for direction 1: fetch ward-level results and build units.

    fetch   download every ballot of the training rounds, keeping ward ids
            and candidate ids (cached under data/forecast/, gitignored)
    units   build one row per ward contest x party, with the previous
            result, the cold-start flag and contest features

A unit is (round, council, ward contest at t, party). Its outcome is the
party's vote share at t, using the top-candidate method in multi-member
wards. Every feature comes from the t-1 election or from the line-up at t
(candidates are published weeks before polling day), never from t's votes.

Usage:
  PYTHONPATH=.:src python -m forecast.elections fetch
  PYTHONPATH=.:src python -m forecast.elections units
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

from v2_design.incumbent_power import ROUNDS, list_elections, normalise_party

DC_API = "https://candidates.democracyclub.org.uk/api/next/ballots/"
CACHE = Path("data/forecast")
UNITS_CSV = CACHE / "units_train.csv"
RESERVED_FROM_YEAR = 2024        # the 2025 test round is fetched only after freeze

# Parties modelled individually, by Electoral Commission id. Every other
# party and all independents are pooled as "OTH" so that each contest's
# shares still sum to 100.
PARTIES = {
    "PP52": "CON", "PP53": "LAB", "PP90": "LD", "PP63": "GRN",
    "PP7931": "REF", "PP85": "UKIP",
}


# --- fetch ---------------------------------------------------------------------------

def _get(url, params=None):
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"failed: {url} {params}")


def fetch_ballots(election_id: str) -> list[dict]:
    """Every ballot of one election, with the ids needed for matching."""
    if int(election_id[-10:-6]) >= RESERVED_FROM_YEAR:
        raise PermissionError(f"{election_id} is reserved for the test round")
    cache = CACHE / f"ballots_{election_id}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    out, url = [], DC_API
    params = {"election_id": election_id, "page_size": 200}
    while url:
        body = _get(url, params)
        for b in body["results"]:
            if b.get("cancelled"):
                continue
            out.append({
                "ballot_id": b["ballot_paper_id"],
                # By-elections share an election id with scheduled
                # contests on the same day; ".by." in the ballot id marks
                # them so they can be dropped ballot by ballot.
                "by_election": ".by." in b["ballot_paper_id"],
                "ward_id": b["post"]["id"],          # GSS code where known
                "ward_label": b["post"]["label"],
                "winner_count": b["winner_count"],
                "candidates": [{
                    "person_id": (c.get("person") or {}).get("id"),
                    "party": (c.get("party") or {}).get("ec_id")
                             or (c.get("party") or {}).get("name")
                             or c.get("party_name") or "unknown",
                    "votes": (c.get("result") or {}).get("num_ballots"),
                    "elected": bool((c.get("result") or {}).get("elected")
                                    or c.get("elected")),
                } for c in b["candidacies"]],
            })
        url, params = body.get("next"), None
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    time.sleep(1)                     # polite pause: a volunteer-run service
    return out


def stage_fetch() -> None:
    for name, (d0, d1) in ROUNDS.items():
        e0 = {e["slug"]: e for e in list_elections(d0)}
        e1 = {e["slug"]: e for e in list_elections(d1)}
        both = sorted(set(e0) & set(e1))
        print(f"{name}: {len(both)} councils", flush=True)
        for slug in both:
            fetch_ballots(e0[slug]["election_id"])
            fetch_ballots(e1[slug]["election_id"])


# --- building units -------------------------------------------------------------------

def party_code(raw: str) -> str:
    """Electoral Commission id -> modelled party code, or OTH."""
    return PARTIES.get(normalise_party(raw), "OTH")


def contested(ballot: dict) -> bool:
    """A contest took place only if there were more candidates than seats."""
    return len(ballot["candidates"]) > ballot["winner_count"]


def best_votes(ballot: dict) -> dict[str, int] | None:
    """Votes of each party's best-placed candidate in one ward, by code.

    In a multi-member ward each voter has several votes, so each party is
    represented by its best-placed candidate only (the top-candidate
    method). Independents and minor parties are not one party: each is kept
    separately and then summed into OTH. Returns None if a count is missing.
    """
    best: dict[str, int] = {}
    for c in ballot["candidates"]:
        if c["votes"] is None:
            return None
        code = party_code(c["party"])
        key = code if code != "OTH" else f"OTH:{c['party']}:{c['person_id']}"
        best[key] = max(best.get(key, 0), c["votes"])
    out: Counter = Counter()
    for key, v in best.items():
        out["OTH" if key.startswith("OTH:") else key] += v
    return dict(out)


def ward_shares(ballot: dict) -> dict[str, float] | None:
    """Party shares (%) in one ward, top-candidate method."""
    votes = best_votes(ballot)
    total = sum(votes.values()) if votes else 0
    return {k: 100 * v / total for k, v in votes.items()} if total else None


def council_shares(ballots: list[dict]) -> dict[str, float]:
    """Council-wide shares at t-1, summing best votes over contested wards.
    Used as the previous result when a ward's boundaries changed."""
    totals: Counter = Counter()
    for b in ballots:
        if b["by_election"] or not contested(b):
            continue
        votes = best_votes(b)
        if votes:
            totals.update(votes)
    grand = sum(totals.values())
    return {k: 100 * v / grand for k, v in totals.items()} if grand else {}


def controlling_party(ballots: list[dict]) -> str:
    """Seat majority at t-1, or "" if none. Only meaningful for whole-council
    elections; for councils elected by thirds it is left to the model to
    treat as missing (council_whole_prev = 0)."""
    seats = Counter(party_code(c["party"]) for b in ballots
                    if not b["by_election"]
                    for c in b["candidates"] if c["elected"])
    total = sum(seats.values())
    if not total:
        return ""
    party, won = seats.most_common(1)[0]
    return party if won > total / 2 and party != "OTH" else ""


def _norm(label: str) -> str:
    """Ward name reduced to lower-case letters and digits, for matching."""
    return "".join(ch for ch in label.lower() if ch.isalnum())


def build_round(round_name: str, slug: str, subtype: str,
                prev: list[dict], curr: list[dict],
                polls_prev: dict | None = None,
                polls_curr: dict | None = None) -> list[dict]:
    """Unit rows for one council in one round.

    `polls_prev` / `polls_curr` map party code -> national poll average in
    the 14 days before the t-1 / t polling day (forecast.polls). A party a
    pollster did not report (OTH; UKIP after 2020) is left blank.
    """
    polls_prev, polls_curr = polls_prev or {}, polls_curr or {}
    from v2_design.incumbent_power import is_whole_council
    prev_sched = [b for b in prev if not b["by_election"]]
    curr_sched = [b for b in curr if not b["by_election"] and contested(b)]
    # A missing ward id cannot identify a ward, so it is never id-matched.
    by_ward = {b["ward_id"]: b for b in prev_sched if b["ward_id"]}
    # Older elections use local ward ids ("KEN:ashford-central") where later
    # ones use GSS codes ("gss:E58001724"), so the same ward fails an id
    # match. For those old-style ids only, fall back to the ward name,
    # provided the name is unique in the council. Two different GSS codes
    # mean the boundary really changed (a new code is issued), so a GSS ward
    # is never matched by name.
    label_counts = Counter(_norm(b["ward_label"]) for b in prev_sched)
    by_label = {_norm(b["ward_label"]): b for b in prev_sched
                if not (b["ward_id"] or "").startswith("gss:")
                and label_counts[_norm(b["ward_label"])] == 1}
    fallback = council_shares(prev_sched)
    control = controlling_party(prev_sched)
    whole_prev = int(is_whole_council(prev_sched, subtype))
    prev_winners = {c["person_id"] for b in prev_sched
                    for c in b["candidates"] if c["elected"]}

    rows = []
    for b in curr_sched:
        outcome = ward_shares(b)
        if outcome is None:
            continue
        match = by_ward.get(b["ward_id"]) if b["ward_id"] else None
        match_type = "id"
        if match is None:
            match, match_type = by_label.get(_norm(b["ward_label"])), "label"
        prev_s = ward_shares(match) if match and contested(match) else None
        boundary_fallback = int(prev_s is None)
        if boundary_fallback:
            match_type = "fallback"
        if prev_s is None:
            prev_s = fallback
        prev_parties = ({party_code(c["party"]) for c in match["candidates"]}
                        if match else set())
        standing = Counter(party_code(c["party"]) for c in b["candidates"])
        for code in sorted(standing):
            rows.append({
                "round": round_name, "council": slug, "subtype": subtype,
                "ballot_id": b["ballot_id"], "ward_id": b["ward_id"],
                "party": code,
                # --- features: from t-1, or the published line-up at t ---
                "share_prev": round(prev_s.get(code, 0.0), 4),
                "boundary_fallback": boundary_fallback,
                "match_type": match_type,      # id | label | fallback
                # Cold start: the party did not stand in this ward last time.
                # Under a boundary fallback the ward's history is unknown,
                # so cold start falls back to "absent council-wide".
                "cold_start": int(code not in prev_parties if match
                                  else fallback.get(code, 0.0) == 0.0),
                "incumbent_standing": int(any(
                    c["person_id"] in prev_winners for c in b["candidates"]
                    if party_code(c["party"]) == code)),
                "n_candidates": len(b["candidates"]),
                "n_party_candidates": standing[code],
                "winner_count": b["winner_count"],
                "controls_council_prev": int(control == code),
                "council_whole_prev": whole_prev,
                # Council-wide t-1 share of the populist-right family
                # (UKIP and Reform/Brexit Party): the nearest thing a new
                # Reform candidacy has to a history of its own.
                "insurgent_council_prev": round(
                    fallback.get("UKIP", 0.0) + fallback.get("REF", 0.0), 4),
                "poll_prev": _fmt(polls_prev.get(code)),
                "poll_curr": _fmt(polls_curr.get(code)),
                "poll_change": _fmt(
                    polls_curr[code] - polls_prev[code]
                    if polls_curr.get(code) is not None
                    and polls_prev.get(code) is not None else None),
                # --- outcome ---
                "share": round(outcome.get(code, 0.0), 4),
            })
    return rows


def _fmt(value: float | None) -> str | float:
    return "" if value is None else round(value, 3)


def _poll_map(polls: list[dict], day: str) -> dict:
    from forecast.polls import poll_average
    out = {}
    for code in set(PARTIES.values()):
        value = poll_average(polls, day, code)
        if value is not None:
            out[code] = value
    return out


def stage_units() -> None:
    from forecast.polls import load_polls
    polls = load_polls()
    rows = []
    for name, (d0, d1) in ROUNDS.items():
        p0, p1 = _poll_map(polls, d0), _poll_map(polls, d1)
        e0 = {e["slug"]: e for e in list_elections(d0)}
        e1 = {e["slug"]: e for e in list_elections(d1)}
        for slug in sorted(set(e0) & set(e1)):
            rows += build_round(name, slug, e1[slug]["subtype"],
                                fetch_ballots(e0[slug]["election_id"]),
                                fetch_ballots(e1[slug]["election_id"]),
                                polls_prev=p0, polls_curr=p1)
    with UNITS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"-> {UNITS_CSV}: {len(rows)} units")


if __name__ == "__main__":
    {"fetch": stage_fetch, "units": stage_units}[sys.argv[1]]()
