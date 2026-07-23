"""Per-division diagnostics for the ward-tier stage (Stage C/D/M).

The corpus-wide diagnostics generator (make_collection_report.py)
breaks the collection down by election and by source, but never by
which of the 17 pre-registered divisions (news_protocol/
division_sample.md) an article actually belongs to. For a paper whose
central design choice is "we collect ward-level news for a
pre-registered representative sample of divisions", that per-division
breakdown is the evidence the sampling design actually worked - not
an optional extra.

Why this has to be computed here rather than read off a record field:
raw_news_schema.json deliberately has no "ward" field on the article
record itself (see raw_news_schema.md - the schema stores only what
was actually retrieved and its provenance, and "which division this
article was searched FOR" is a fact about the SEARCH, not a fact
about the article's content). The join back to a division therefore
goes: article record -> retrieval.search_query_id -> one row of
news_collection/search_log.csv -> that row's ward column (itself
copied from the query inventory at collection time). This keeps the
schema's own "no invented associations" rule intact: an article is
only linked to a division because a logged, ward-scoped search is
what found it, and that link is auditable end to end.

Usage:
    python3 -m src.news_collection.make_ward_tier_report
"""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

RECORDS = Path("data/raw/news/records")
LOG = Path("news_collection/search_log.csv")
SAMPLE = Path("news_protocol/division_sample.csv")
OUT = Path("news_collection/ward_tier_diagnostics.json")


def load_query_to_ward():
    """query_id -> (ward, election_id) for every ward-tier search that
    has actually been executed and logged - not the full inventory, so
    a query that was planned but never run correctly contributes
    nothing here (searches, not plans, are what produced articles)."""
    mapping = {}
    for r in csv.DictReader(LOG.open()):
        if r["ward"]:
            mapping[r["query_id"]] = (r["ward"], r["election_id"])
    return mapping


def main():
    sampled_divisions = ([r["division"] for r in csv.DictReader(SAMPLE.open())]
                         if SAMPLE.exists() else [])
    query_to_ward = load_query_to_ward()

    # Walk every stored record once, and for each one that was found by
    # a ward-scoped search, attribute it to that division/election pair.
    by_division = defaultdict(lambda: {
        "records": 0, "by_election": Counter(),
        "date_confidence": Counter(), "sources": Counter(),
    })
    unattributed = 0   # records whose query wasn't ward-scoped (county/national arm)
    for path in RECORDS.glob("*.json"):
        rec = json.loads(path.read_text())
        qid = rec["retrieval"]["search_query_id"]
        hit = query_to_ward.get(qid)
        if hit is None:
            unattributed += 1
            continue
        ward, eid = hit
        d = by_division[ward]
        d["records"] += 1
        d["by_election"][eid] += 1
        d["date_confidence"][rec["dates"]["date_confidence"]] += 1
        d["sources"][rec["source_id"]] += 1

    # Report every SAMPLED division even if it has zero articles so
    # far - a silent absence would be indistinguishable from "not
    # collected yet", and this script's whole purpose is to make that
    # visible, not hide it inside a Counter that only shows what exists.
    report = {"generated_for": "Stage C first execution",
             "sampled_divisions": len(sampled_divisions),
             "divisions_with_at_least_one_record": 0,
             "divisions": {}}
    for division in sorted(sampled_divisions):
        d = by_division.get(division)
        if d is None:
            report["divisions"][division] = {
                "records": 0, "by_election": {}, "date_confidence": {},
                "sources": {}, "note": "no records yet for this division",
            }
            continue
        report["divisions_with_at_least_one_record"] += 1
        report["divisions"][division] = {
            "records": d["records"],
            "by_election": dict(d["by_election"]),
            "date_confidence": dict(d["date_confidence"]),
            "sources": dict(d["sources"]),
        }
    report["unattributed_records_skipped"] = unattributed

    OUT.write_text(json.dumps(report, indent=2))
    total = sum(v["records"] for v in report["divisions"].values())
    print(f"{total} ward-attributed records across "
          f"{report['divisions_with_at_least_one_record']}/"
          f"{report['sampled_divisions']} sampled divisions -> {OUT}")
    for division, d in sorted(report["divisions"].items()):
        print(f"  {division}: {d['records']} records "
              f"{d.get('by_election', {})}")


if __name__ == "__main__":
    main()
