"""Who does local news name? Coverage by candidate type (Kent, Surrey 2021).

    PYTHONPATH=.:src python -m forecast.candidate_coverage run

The ward coverage run found that the candidates local news names are
mostly sitting councillors. Reform's 2025 slate was largely new and outside
the main parties, so the question for a Reform cold-start test is how often
local news names THAT kind of candidate. In 2021, the nearest analogue is a
candidate who is new to the council (did not stand for it in 2017) and from
a minor party (not Conservative, Labour or Lib Dem; independents included).

Candidates are classified from Democracy Club records (names, parties,
2017 candidacies and winners; matched by Democracy Club's person id) and
checked against the same window articles, with the same full-name rule, as
forecast.ward_coverage. Decision rule: ward_coverage_v1/criteria.md, A1.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import requests

from forecast import ward_coverage as wc
from v2_design import keyword_prefilter as kp
from v2_design.incumbent_power import normalise_party

DATA = wc.DATA
OUT = wc.OUT_DIR / "candidate_coverage.json"
ELECTIONS = {
    "surrey": ("local.surrey.2017-05-04", "local.surrey.2021-05-06"),
    "kent": ("local.kent.2017-05-04", "local.kent.2021-05-06"),
}
MAJOR = {"PP52", "PP53", "PP90"}           # Conservative, Labour, Lib Dem
INSURGENT = {"PP7931", "PP85"}             # Reform UK, UKIP


def candidates(election_id: str) -> list[dict]:
    """Every candidacy in one election: person id, name, party, elected.
    Cached; by-elections and cancelled ballots are dropped."""
    cache = DATA / f"candidates_{election_id}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    out, url = [], wc.DC_API
    params = {"election_id": election_id, "page_size": 200}
    while url:
        body = requests.get(url, params=params, timeout=120).json()
        for b in body["results"]:
            if b.get("cancelled") or ".by." in b["ballot_paper_id"]:
                continue
            for c in b["candidacies"]:
                person = c.get("person") or {}
                party = (c.get("party") or {})
                out.append({
                    "ballot": b["ballot_paper_id"],
                    "person_id": person.get("id"),
                    "name": person.get("name", ""),
                    "party": normalise_party(party.get("ec_id")
                                             or party.get("name") or ""),
                    "elected": bool((c.get("result") or {}).get("elected")
                                    or c.get("elected")),
                })
        url, params = body.get("next"), None
    DATA.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


def classify(c2021: list[dict], c2017: list[dict]) -> list[dict]:
    """Tag each 2021 candidacy with its type.

    incumbent  won a seat on the same council in 2017
    past       stood for the same council in 2017 and lost
    new        did not stand for the same council in 2017
    Then minor = not Conservative / Labour / Lib Dem.
    """
    stood = {c["person_id"] for c in c2017}
    won = {c["person_id"] for c in c2017 if c["elected"]}
    out = []
    for c in c2021:
        history = ("incumbent" if c["person_id"] in won
                   else "past" if c["person_id"] in stood else "new")
        out.append({**c, "history": history,
                    "minor": c["party"] not in MAJOR,
                    "insurgent": c["party"] in INSURGENT})
    return out


def named_counts(cands: list[dict], articles: list[dict]) -> dict:
    """person_id -> number of window articles naming the candidate in full.
    Names of one word are skipped (too ambiguous to match safely)."""
    counts = defaultdict(int)
    texts = [kp.article_text(a["headline"], a["text"]) for a in articles]
    for c in cands:
        if len(c["name"].split()) < 2:
            continue
        counts[c["person_id"]] = sum(wc._has(t, c["name"]) for t in texts)
    return counts


def share_named(group: list[dict], counts: dict) -> dict:
    n = len(group)
    named = sum(counts.get(c["person_id"], 0) >= 1 for c in group)
    return {"candidates": n,
            "named_share": round(named / n, 3) if n else None,
            "named_3plus_share": round(sum(
                counts.get(c["person_id"], 0) >= 3 for c in group) / n, 3)
                if n else None}


def stage_run() -> None:
    import csv
    from v2_design import outlet_pilot as pilot
    with wc.TARGETS.open(encoding="utf-8") as handle:
        targets = list(csv.DictReader(handle))
    articles = defaultdict(list)                 # county -> window articles
    for row in targets:
        path = pilot._cache_path(row)
        if path.exists():
            a = json.loads(path.read_text())
            if a.get("text") and pilot.in_window(a):
                articles[a["council"]].append(a)

    tagged, counts = [], {}
    for county, (e2017, e2021) in ELECTIONS.items():
        cands = classify(candidates(e2021), candidates(e2017))
        counts.update(named_counts(cands, articles[county]))
        tagged += cands

    groups = {
        "incumbent": [c for c in tagged if c["history"] == "incumbent"],
        "past": [c for c in tagged if c["history"] == "past"],
        "new_major": [c for c in tagged
                      if c["history"] == "new" and not c["minor"]],
        "new_minor (N1)": [c for c in tagged
                           if c["history"] == "new" and c["minor"]],
        "reform_or_ukip": [c for c in tagged if c["insurgent"]],
    }
    result = {name: share_named(g, counts) for name, g in groups.items()}
    n1 = result["new_minor (N1)"]["named_share"]
    decision = ("design a ward-level hypothesis" if n1 >= 0.50
                else "design only if a power check can pass" if n1 >= 0.25
                else "stop: the news strand closes")
    payload = {"criteria": "v2_design/ward_coverage_v1/criteria.md (A1)",
               "window_articles": {k: len(v) for k, v in articles.items()},
               "groups": result, "N1": n1, "decision": decision}
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    {"run": stage_run}[sys.argv[1]]()
