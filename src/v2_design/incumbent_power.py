"""Direction A, results-only power check (no news, no paid API).

Question: if local coverage of council performance moves the controlling
party's vote share, how big would that effect have to be for V2 to detect it?
The answer needs election results only:

  1. list English whole-council elections in three rounds
     (2017->2021, 2018->2022, 2019->2023) from Democracy Club;
  2. find each council's controlling party at t-1 (a majority of seats);
  3. measure that party's council-wide vote-share change from t-1 to t;
  4. predict it with a no-news baseline (national swing, previous share)
     under leave-one-council-out cross-validation;
  5. turn the residual spread into a minimum detectable effect (MDE80).

Usage:
  PYTHONPATH=.:src python -m v2_design.incumbent_power fetch   # cached
  PYTHONPATH=.:src python -m v2_design.incumbent_power analyse

Every election from 2024 onwards is reserved for V2's confirmatory test and
is never requested. Criteria: v2_design/incumbent_power_v1/criteria.md.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import requests

EE_API = "https://elections.democracyclub.org.uk/api/elections/"
DC_API = "https://candidates.democracyclub.org.uk/api/next/ballots/"
CACHE = Path("data/v2_incumbent")             # raw results, gitignored
OUT_DIR = Path("v2_design/incumbent_power_v1")

# (t-1 polling day, t polling day). Each pair is one "round".
ROUNDS = {
    "2017-2021": ("2017-05-04", "2021-05-06"),
    "2018-2022": ("2018-05-03", "2022-05-05"),
    "2019-2023": ("2019-05-02", "2023-05-04"),
}
RESERVED_FROM_YEAR = 2024   # never fetch anything at or after this year

Z80 = 1.959964 + 0.841621   # two-sided 5% + 80% power
SMALLEST_EFFECT_OF_INTEREST = 1.0   # pp per SD of the news feature


# --- fetching (cached) ----------------------------------------------------------

def _get(url: str, params: dict | None = None) -> dict:
    """GET with polite retries. Democracy Club is a free volunteer service."""
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"failed: {url} {params}")


def list_elections(day: str) -> list[dict]:
    """English council-level local elections on one polling day."""
    assert int(day[:4]) < RESERVED_FROM_YEAR, "reserved election requested"
    cache = CACHE / f"elections_{day}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    out, url = [], EE_API
    params = {"poll_open_date": day, "election_type": "local",
              "identifier_type": "organisation", "limit": 200}
    while url:
        body = _get(url, params)
        for e in body["results"]:
            org = e.get("organisation") or {}
            # England only (Wales and Scotland run different systems), and
            # skip cancelled or deleted elections.
            if org.get("territory_code") != "ENG" or e.get("cancelled") \
                    or e.get("deleted"):
                continue
            out.append({"election_id": e["election_id"],
                        "slug": org.get("slug"),
                        "subtype": org.get("organisation_subtype")})
        url, params = body.get("next"), None   # `next` already has the query
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


def fetch_ballots(election_id: str) -> list[dict]:
    """Every ballot of one election, reduced to what the analysis needs."""
    assert int(election_id[-10:-6]) < RESERVED_FROM_YEAR, election_id
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
                "winner_count": b["winner_count"],
                "candidates": [{
                    # The Electoral Commission id identifies a party exactly,
                    # whatever name variant the candidate stood under.
                    # Independents have no ec_id and are kept apart by name.
                    "party": (c.get("party") or {}).get("ec_id")
                             or (c.get("party") or {}).get("name")
                             or c.get("party_name") or "unknown",
                    "votes": (c.get("result") or {}).get("num_ballots"),
                    "elected": bool((c.get("result") or {}).get("elected")
                                    or c.get("elected")),
                } for c in b["candidacies"]],
            })
        url, params = body.get("next"), None
    cache.write_text(json.dumps(out))
    time.sleep(1)   # polite pause between elections
    return out


def stage_fetch() -> None:
    for name, (d0, d1) in ROUNDS.items():
        e0 = {e["slug"]: e for e in list_elections(d0)}
        e1 = {e["slug"]: e for e in list_elections(d1)}
        both = sorted(set(e0) & set(e1))
        print(f"{name}: {len(both)} councils voted in both years", flush=True)
        for slug in both:
            fetch_ballots(e0[slug]["election_id"])
            fetch_ballots(e1[slug]["election_id"])


# --- building units ---------------------------------------------------------------

def is_whole_council(ballots: list[dict], subtype: str | None) -> bool:
    """Criteria rule: counties and London boroughs always elect the whole
    council. Otherwise require that at least 30% of ballots elect more than
    one member, which councils elected by thirds almost never do."""
    if subtype in ("CTY", "LBO"):
        return True
    if not ballots:
        return False
    multi = sum(1 for b in ballots if b["winner_count"] > 1)
    return multi / len(ballots) >= 0.30


def controlling_party(ballots: list[dict]) -> str | None:
    """Party holding more than half the seats won, or None (no control)."""
    seats = Counter(c["party"] for b in ballots for c in b["candidates"]
                    if c["elected"])
    total = sum(seats.values())
    if not total:
        return None
    party, won = seats.most_common(1)[0]
    return party if won > total / 2 else None


def vote_shares(ballots: list[dict]) -> dict[str, float] | None:
    """Council-wide shares (%) by the top-candidate method.

    In a multi-member ward every voter casts several votes, so summing all
    candidates would over-count parties that field full slates. Taking each
    party's best-placed candidate per ballot counts each party once per ward.
    Returns None if any contested ballot lacks vote counts.
    """
    totals: Counter = Counter()
    for b in ballots:
        if len(b["candidates"]) <= b["winner_count"]:
            continue   # uncontested: no votes were cast
        best: dict[str, int] = {}
        for c in b["candidates"]:
            if c["votes"] is None:
                return None
            best[c["party"]] = max(best.get(c["party"], 0), c["votes"])
        totals.update(best)
    grand = sum(totals.values())
    return {p: 100 * v / grand for p, v in totals.items()} if grand else None


def build_units() -> tuple[list[dict], dict]:
    units, excluded = [], Counter()
    for name, (d0, d1) in ROUNDS.items():
        e0 = {e["slug"]: e for e in list_elections(d0)}
        e1 = {e["slug"]: e for e in list_elections(d1)}
        for slug in sorted(set(e0) & set(e1)):
            b0 = fetch_ballots(e0[slug]["election_id"])
            b1 = fetch_ballots(e1[slug]["election_id"])
            if not (is_whole_council(b0, e0[slug]["subtype"])
                    and is_whole_council(b1, e1[slug]["subtype"])):
                excluded["not_whole_council"] += 1
                continue
            party = controlling_party(b0)
            if party is None:
                excluded["no_overall_control"] += 1
                continue
            s0, s1 = vote_shares(b0), vote_shares(b1)
            if s0 is None or s1 is None or party not in s0:
                excluded["missing_results"] += 1
                continue
            units.append({"round": name, "council": slug, "party": party,
                          "share_prev": s0[party],
                          "change": s1.get(party, 0.0) - s0[party],
                          "all_changes": {p: s1.get(p, 0.0) - s0.get(p, 0.0)
                                          for p in set(s0) | set(s1)}})
    return units, dict(excluded)


# --- analysis ---------------------------------------------------------------------

def national_swing_loo(units: list[dict]) -> np.ndarray:
    """For each unit: the same party's mean share change, same round, across
    every OTHER council in the round (not just councils it controls). Leaving
    the unit out stops its own result leaking into its own baseline."""
    by_round_party = defaultdict(list)   # (round, party) -> [(council, change)]
    for u in units:
        for p, ch in u["all_changes"].items():
            by_round_party[(u["round"], p)].append((u["council"], ch))
    out = []
    for u in units:
        others = [ch for c, ch in by_round_party[(u["round"], u["party"])]
                  if c != u["council"]]
        out.append(np.mean(others) if others else 0.0)
    return np.array(out)


def loo_residuals(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Leave-one-council-out OLS residuals (intercept added)."""
    X1 = np.column_stack([np.ones(len(y)), X])
    res = np.empty(len(y))
    for i in range(len(y)):
        keep = np.arange(len(y)) != i
        beta, *_ = np.linalg.lstsq(X1[keep], y[keep], rcond=None)
        res[i] = y[i] - X1[i] @ beta
    return res


def mde80(sigma: float, n: int) -> float:
    return Z80 * sigma / np.sqrt(n) if n else float("nan")


def verdict(mde: float) -> str:
    if mde <= SMALLEST_EFFECT_OF_INTEREST:
        return "proceed"
    if mde <= 2 * SMALLEST_EFFECT_OF_INTEREST:
        return "proceed with pooling only"
    return "stop direction A"


def stage_analyse() -> None:
    units, excluded = build_units()
    y = np.array([u["change"] for u in units])
    X = np.column_stack([national_swing_loo(units),
                         [u["share_prev"] for u in units]])
    res = loo_residuals(X, y)
    sigma = float(res.std(ddof=1))
    r2 = float(1 - (res ** 2).sum() / ((y - y.mean()) ** 2).sum())
    per_round = Counter(u["round"] for u in units)
    one_round = int(np.median(list(per_round.values())))
    payload = {
        "criteria": "v2_design/incumbent_power_v1/criteria.md",
        "units": len(units), "units_per_round": dict(per_round),
        "excluded": excluded,
        "controlling_parties": dict(Counter(u["party"] for u in units)),
        "outcome_sd_pp": round(float(y.std(ddof=1)), 3),
        "baseline_cv_r2": round(r2, 3),
        "residual_sigma_pp": round(sigma, 3),
        "mde80_pooled_pp_per_sd": round(mde80(sigma, len(units)), 3),
        "mde80_one_round_pp_per_sd": round(mde80(sigma, one_round), 3),
        "one_round_n": one_round,
        "verdict_on_one_round": verdict(mde80(sigma, one_round)),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "incumbent_power_results.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    {"fetch": stage_fetch, "analyse": stage_analyse}[sys.argv[1]]()
