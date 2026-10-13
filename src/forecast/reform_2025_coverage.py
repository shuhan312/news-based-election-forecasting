"""Amendment A3: does local news name Kent's 2025 Reform candidates?

    PYTHONPATH=.:src python -m forecast.reform_2025_coverage candidates
    PYTHONPATH=.:src python -m forecast.reform_2025_coverage targets
    PYTHONPATH=.:src python -m forecast.reform_2025_coverage fetch
    PYTHONPATH=.:src python -m forecast.reform_2025_coverage match

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


def stage_match() -> None:
    cands = [c for c in json.loads((DATA / "candidates_2025.json").read_text())
             if c["party"] == REFORM]
    with (DATA / "targets.csv").open(encoding="utf-8") as h:
        targets = list(csv.DictReader(h))
    texts = []
    for row in targets:
        path = pilot._cache_path(row)
        if path.exists():
            a = json.loads(path.read_text())
            if a.get("text") and in_window(a):
                texts.append(wc.kp.article_text(a["headline"], a["text"]))
    counts, how = {}, {}
    for c in cands:
        hits = [named(t, c["name"]) for t in texts]
        counts[c["person_id"]] = sum(h is not None for h in hits)
        how[c["person_id"]] = ("full" if "full" in hits
                               else "surname" if "surname" in hits else None)

    def share(group, k=1):
        return round(sum(counts[c["person_id"]] >= k for c in group)
                     / len(group), 3) if group else None

    new = [c for c in cands if c["new"]]
    r1 = share(cands)
    decision = ("design a ward-level hypothesis" if r1 >= 0.50
                else "design only if a power check can pass" if r1 >= 0.25
                else "stop: the news strand closes")
    payload = {
        "criteria": "v2_design/ward_coverage_v1/criteria.md (A3)",
        "window_articles": len(texts), "reform_candidates": len(cands),
        "R1_named_share": r1, "named_3plus_share": share(cands, 3),
        "named_by_full_name": sum(v == "full" for v in how.values()),
        "named_by_surname_near_reform_only": sum(v == "surname"
                                                 for v in how.values()),
        "new_reform_candidates": len(new), "new_named_share": share(new),
        "decision": decision,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    {"candidates": stage_candidates, "targets": stage_targets,
     "fetch": stage_fetch, "match": stage_match}[sys.argv[1]]()
