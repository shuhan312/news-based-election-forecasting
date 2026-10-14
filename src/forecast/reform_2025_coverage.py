"""Amendment A3: does local news name Kent's 2025 Reform candidates?

    PYTHONPATH=.:src python -m forecast.reform_2025_coverage candidates
    PYTHONPATH=.:src python -m forecast.reform_2025_coverage targets
    PYTHONPATH=.:src python -m forecast.reform_2025_coverage bound
    PYTHONPATH=.:src python -m forecast.reform_2025_coverage fetch
    PYTHONPATH=.:src python -m forecast.reform_2025_coverage check    # window dates
    PYTHONPATH=.:src python -m forecast.reform_2025_coverage match
    PYTHONPATH=.:src python -m forecast.reform_2025_coverage decide   # A5

The decisive check for a ward-level news hypothesis. It measures the real
population, Reform's 2025 candidates, instead of a 2021 proxy, using only
pre-election information:

  - the 2025 candidate list (published in early April 2025);
  - local articles published 1-30 April 2025 (30-1 days before polling).

No 2025 result is read. Democracy Club's ballot response also carries
results, so `strip_results` keeps only ballot, person id, name and party at
read time. Nothing else is stored, and no vote or elected flag is printed.

Criteria: v2_design/ward_coverage_v1/criteria.md, amendment A3.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests

from forecast import ward_coverage as wc
from v2_design import outlet_pilot as pilot
from v2_design.incumbent_power import normalise_party

DATA = Path("data/reform_2025")                      # gitignored
OUT = wc.OUT_DIR / "reform_2025_coverage.json"
ELECTION_2025 = "local.kent.2025-05-01"
ELECTION_2021 = "local.kent.2021-05-06"
REFORM = "PP7931"

PUB_START, PUB_END = date(2025, 4, 1), date(2025, 4, 30)   # 30-1 days
CAP_START, CAP_END = date(2025, 4, 1), date(2025, 5, 31)   # archive lag
KENT_OUTLETS = [("kentlive.news/news/", "prefix"),
                ("bbc.co.uk/news/uk-england-kent", "prefix"),
                ("kentonline.co.uk", "sections")]
PROXIMITY = 100          # max characters between surname and "Reform"
# Amendment A4: an article naming this many candidates or more is a
# candidate list. It says only who is standing, which the official list
# already says, so it carries no news content and does not count.
LIST_MIN = 10


# --- 1. candidates, with results stripped at read time ----------------------------------

KEEP = ("ballot", "person_id", "name", "party")


def strip_results(ballot: dict) -> list[dict]:
    """One record per candidacy holding only KEEP fields. Votes, elected
    flags and every other result field are dropped here, before anything is
    stored, so no 2025 outcome can reach a later stage."""
    out = []
    for c in ballot.get("candidacies", []):
        party = c.get("party") or {}
        out.append({
            "ballot": ballot["ballot_paper_id"],
            "person_id": (c.get("person") or {}).get("id"),
            "name": (c.get("person") or {}).get("name", ""),
            "party": normalise_party(party.get("ec_id")
                                     or party.get("name") or ""),
        })
    return out


def stage_candidates() -> None:
    """Kent's 2025 candidates (results stripped) and the 2021 person ids,
    to tell new Reform candidates from returning ones."""
    def fetch(eid: str) -> list[dict]:
        rows, url = [], wc.DC_API
        params = {"election_id": eid, "page_size": 200}
        while url:
            body = requests.get(url, params=params, timeout=120).json()
            for b in body["results"]:
                if b.get("cancelled") or ".by." in b["ballot_paper_id"]:
                    continue
                rows += strip_results(b)
            url, params = body.get("next"), None
        return rows
    DATA.mkdir(parents=True, exist_ok=True)
    c2025 = fetch(ELECTION_2025)
    stood_2021 = {r["person_id"] for r in fetch(ELECTION_2021)}
    for r in c2025:
        r["new"] = r["person_id"] not in stood_2021
    (DATA / "candidates_2025.json").write_text(json.dumps(c2025))
    reform = [r for r in c2025 if r["party"] == REFORM]
    print(f"{len(c2025)} candidacies; {len(reform)} Reform UK, "
          f"{sum(r['new'] for r in reform)} new to Kent since 2021")


# --- 2-3. articles published 1-30 April 2025 ---------------------------------------------

def _cdx_2025(target: str, match: str) -> list[tuple[str, str]]:
    """Archived URLs captured 1 Apr - 31 May 2025 (cached; weekly chunks,
    KentOnline by town section)."""
    slug = re.sub(r"[^a-z0-9]+", "_", target)
    pilot.CACHE.mkdir(parents=True, exist_ok=True)
    if match == "sections":
        out = []
        for section in pilot.KENTONLINE_SECTIONS:
            path = pilot.CACHE / f"cdx_{slug}_{section}_2025.json"
            if not path.exists():
                path.write_text(json.dumps(pilot._cdx_chunk(
                    f"{target}/{section}/news/", "prefix", CAP_START, CAP_END)))
            out += [tuple(x) for x in json.loads(path.read_text())]
        return out
    out, start = [], CAP_START
    while start <= CAP_END:
        end = min(date.fromordinal(start.toordinal() + 6), CAP_END)
        path = pilot.CACHE / f"cdx_{slug}_2025_{start:%Y%m%d}.json"
        if not path.exists():
            path.write_text(json.dumps(pilot._cdx_chunk(target, match,
                                                        start, end)))
        out += [tuple(x) for x in json.loads(path.read_text())]
        start = date.fromordinal(end.toordinal() + 1)
    return out


def stage_targets() -> None:
    """Every article-like URL captured in the window, one per article.

    There is no 2025 sample to bound ids with, so nothing is filtered by id;
    the fetched publication date decides membership.
    """
    rows, seen = [], set()
    for target, match in KENT_OUTLETS:
        n = 0
        for ts, url in _cdx_2025(target, match):
            norm = wc._norm_url(url)
            if norm in seen:
                continue
            seen.add(norm)
            rows.append({"council": "kent", "outlet": target,
                         "timestamp": ts, "url": url})
            n += 1
        if n == 0:          # never measure with an outlet silently missing
            raise RuntimeError(f"no 2025 targets for {target}")
    with (DATA / "targets.csv").open("w", newline="", encoding="utf-8") as h:
        writer = csv.DictWriter(h, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} candidate URLs")


SAMPLE_PER_OUTLET = 100


def article_id_2025(url: str) -> int | None:
    """Numeric article id, also reading KentOnline's old formats.

    ward_coverage.article_id reads 6-9 digit ids. KentOnline's older
    articles end in 4-5 digits ('-20201') or an 'a' plus digits
    ('-a96968'); left unread, those ~7,400 old URLs were kept as
    "unbounded". Their ids are far below 2025's (~322,000), so reading
    them lets the bound drop them. The 2021 code is left unchanged so its
    committed results stay reproducible.
    """
    aid = wc.article_id(url)
    if aid is not None:
        return aid
    from urllib.parse import urlparse
    m = re.search(r"-a?(\d{4,9})/?$", urlparse(url).path)
    return int(m.group(1)) if m else None


def stage_bound() -> None:
    """Cut the download list with a sampled article-id lower bound.

    About 24,500 URLs were captured in the window, mostly older articles
    re-crawled; fetching them all takes over seven hours. As in 2021,
    article ids rise with publication date. Fetch a fixed random sample of
    100 URLs per outlet, then set the lower bound to the HIGHEST id among
    sampled articles dated BEFORE 1 April 2025 (capped at the lowest
    in-window id, if that is lower). No upper bound.

    A first version used the lowest in-window sampled id instead. That is
    wrong: with only a few in-window articles in the sample (KentOnline: 4
    of 100), their lowest id is likely mid-April, which would drop early-
    April articles. An article dated before the window is earlier than
    every in-window article, so its id is a safe floor. stage_fetch's
    caller checks afterwards that the earliest fetched in-window article is
    dated at the very start of April.
    """
    import random
    from concurrent.futures import ThreadPoolExecutor
    full = DATA / "targets_full.csv"           # the unbounded list, kept
    with full.open(encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    rng = random.Random(20261014)
    sample = []
    for target, _ in KENT_OUTLETS:
        mine = [r for r in rows if r["outlet"] == target]
        sample += rng.sample(mine, min(SAMPLE_PER_OUTLET, len(mine)))
    with ThreadPoolExecutor(max_workers=wc.WORKERS) as pool:
        list(pool.map(wc._fetch_and_cache, sample))
    kept, report = [], {}
    for target, _ in KENT_OUTLETS:
        before, inside = [], []
        for r in sample:
            if r["outlet"] != target:
                continue
            a = json.loads(pilot._cache_path(r).read_text())
            aid, d = article_id_2025(r["url"]), a.get("published_date")
            if aid is None or not d:
                continue
            if date.fromisoformat(d) < PUB_START:
                before.append(aid)
            elif in_window(a):
                inside.append(aid)
        lo = max(before) if before else 0
        if inside:
            lo = min(lo, min(inside))
        # URLs without a numeric id (e.g. BBC's newer /news/articles/c...
        # format) cannot be bounded, so they are always kept and left to
        # the publication-date filter.
        mine = [r for r in rows if r["outlet"] == target
                and (article_id_2025(r["url"]) is None
                     or article_id_2025(r["url"]) >= lo)]
        kept += mine
        report[target] = {"sampled_before_window": len(before),
                          "sampled_in_window": len(inside),
                          "lower_bound": lo, "kept": len(mine)}
    with (DATA / "targets.csv").open("w", newline="", encoding="utf-8") as h:
        writer = csv.DictWriter(h, fieldnames=list(kept[0]))
        writer.writeheader()
        writer.writerows(kept)
    print(json.dumps(report, indent=1), f"\nkept {len(kept)} of {len(rows)}")


def check_window_start() -> None:
    """Sanity check on dates only (no candidate matching): the earliest
    fetched article dated in the window should be from 1-2 April. A later
    earliest date would mean the lower bound cut early-April articles."""
    with (DATA / "targets.csv").open(encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    by = {}
    for r in rows:
        path = pilot._cache_path(r)
        if path.exists():
            a = json.loads(path.read_text())
            if in_window(a):
                by.setdefault(r["outlet"], []).append(a["published_date"])
    for outlet, dates in by.items():
        print(outlet, "in-window articles", len(dates),
              "earliest", min(dates), "latest", max(dates))


def stage_fetch() -> None:
    from concurrent.futures import ThreadPoolExecutor
    with (DATA / "targets.csv").open(encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    todo = [r for r in rows if not pilot._cache_path(r).exists()]
    print(f"{len(rows) - len(todo)} cached, {len(todo)} to fetch", flush=True)
    with ThreadPoolExecutor(max_workers=wc.WORKERS) as pool:
        for i, _ in enumerate(pool.map(wc._fetch_and_cache, todo)):
            if i % 250 == 0:
                print(f"fetched {i}/{len(todo)}", flush=True)


def in_window(article: dict) -> bool:
    d = article.get("published_date")
    return bool(d) and PUB_START <= date.fromisoformat(d) <= PUB_END


# --- 4. matching -----------------------------------------------------------------------

def named(text: str, full_name: str) -> str | None:
    """'full' if the full name appears; 'surname' if the surname (>= 4
    letters) appears within PROXIMITY characters of "Reform"; else None."""
    if wc._has(text, full_name):
        return "full"
    surname = full_name.split()[-1] if len(full_name.split()) >= 2 else ""
    if len(surname) < 4:
        return None
    for m in re.finditer(r"\b" + re.escape(surname) + r"\b", text,
                         re.IGNORECASE):
        lo, hi = max(0, m.start() - PROXIMITY), m.end() + PROXIMITY
        if re.search(r"\bReform\b", text[lo:hi]):
            return "surname"
    return None


def list_articles(texts: list[str], everyone: list[dict]) -> set[int]:
    """Indices of candidate-list articles: those naming LIST_MIN or more of
    the 2025 candidates (any party) by full name."""
    names = [c["name"] for c in everyone if len(c["name"].split()) >= 2]
    return {i for i, t in enumerate(texts)
            if sum(wc._has(t, n) for n in names) >= LIST_MIN}


def _excerpt(text: str, full_name: str, width: int = 200) -> str:
    """The passage around the candidate's name (or surname), for reading
    in the match check."""
    surname = full_name.split()[-1]
    m = (re.search(re.escape(full_name), text, re.IGNORECASE)
         or re.search(r"\b" + re.escape(surname) + r"\b", text, re.IGNORECASE))
    if not m:
        return ""
    return text[max(0, m.start() - width): m.end() + width]


def stage_match() -> None:
    everyone = json.loads((DATA / "candidates_2025.json").read_text())
    cands = [c for c in everyone if c["party"] == REFORM]
    with (DATA / "targets.csv").open(encoding="utf-8") as h:
        targets = list(csv.DictReader(h))
    texts = []
    for row in targets:
        path = pilot._cache_path(row)
        if path.exists():
            a = json.loads(path.read_text())
            if a.get("text") and in_window(a):
                texts.append(wc.kp.article_text(a["headline"], a["text"]))
    lists = list_articles(texts, everyone)
    counts, counts_all, how = {}, {}, {}
    for c in cands:
        hits = [named(t, c["name"]) for t in texts]
        counts_all[c["person_id"]] = sum(h is not None for h in hits)
        # A4: only non-list articles count towards R1.
        content = [h for i, h in enumerate(hits) if i not in lists]
        counts[c["person_id"]] = sum(h is not None for h in content)
        how[c["person_id"]] = ("full" if "full" in content
                               else "surname" if "surname" in content
                               else None)

    def share(group, k=1, table=None):
        table = counts if table is None else table
        return round(sum(table[c["person_id"]] >= k for c in group)
                     / len(group), 3) if group else None

    new = [c for c in cands if c["new"]]
    r1 = share(cands)
    decision = ("design a ward-level hypothesis" if r1 >= 0.50
                else "design only if a power check can pass" if r1 >= 0.25
                else "stop: the news strand closes")
    # A5 match check: a fixed random sample of the (candidate, article)
    # matches that count towards R1, saved for reading. Article text is
    # written to the gitignored data folder only, never printed.
    import random
    pairs = [(c["person_id"], c["name"], i) for c in cands
             for i, t in enumerate(texts)
             if i not in lists and named(t, c["name"]) is not None]
    sample = random.Random(20261014).sample(pairs, min(20, len(pairs)))
    (DATA / "match_check_sample.json").write_text(json.dumps(
        [{"candidate": name, "how": named(texts[i], name),
          "excerpt": _excerpt(texts[i], name)} for _, name, i in sample],
        indent=1))
    full_only = {c["person_id"]: sum(
        i not in lists and named(t, c["name"]) == "full"
        for i, t in enumerate(texts)) for c in cands}
    payload = {
        "criteria": "v2_design/ward_coverage_v1/criteria.md (A3-A5)",
        "R1_full_name_only (A5 fallback)": share(cands, 1, full_only),
        "match_check_sample": "data/reform_2025/match_check_sample.json",
        "window_articles": len(texts), "list_articles": len(lists),
        "reform_candidates": len(cands),
        "R1_named_share": r1, "named_3plus_share": share(cands, 3),
        "R1_including_lists_not_for_decision": share(cands, 1, counts_all),
        "named_by_full_name": sum(v == "full" for v in how.values()),
        "named_by_surname_near_reform_only": sum(v == "surname"
                                                 for v in how.values()),
        "new_reform_candidates": len(new), "new_named_share": share(new),
        "decision": decision,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


# A5 outcome, entered after reading data/reform_2025/match_check_sample.json.
# One entry per sampled match, in sample order: True = the article really
# names this candidate; False = a different person (verdicts with reasons
# are in coverage_findings.md). Kept in code so the decision is reproducible.
MATCH_CHECK = [True, True, True, False, False, True, False, True, True,
               False, True, True, True, True, False, False, True, True,
               False, True]


def stage_decide() -> None:
    """Apply the A5 rule and the A1/A3 thresholds to the saved R1 figures."""
    payload = json.loads(OUT.read_text())
    false = MATCH_CHECK.count(False)
    # A5: more than 4 false of 20 -> the full-name-only R1 decides.
    use_fallback = false > 4
    r1 = (payload["R1_full_name_only (A5 fallback)"] if use_fallback
          else payload["R1_named_share"])
    payload.update({
        "match_check_false": f"{false}/{len(MATCH_CHECK)}",
        "R1_deciding": r1,
        "R1_deciding_rule": ("full name only (A5 fallback)" if use_fallback
                             else "full name or surname near Reform"),
        "decision": ("design a ward-level hypothesis" if r1 >= 0.50
                     else "design only if a power check can pass"
                     if r1 >= 0.25 else "stop: the news strand closes"),
    })
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    {"candidates": stage_candidates, "targets": stage_targets,
     "bound": stage_bound, "check": check_window_start,
     "fetch": stage_fetch,
     "match": stage_match, "decide": stage_decide}[sys.argv[1]]()
