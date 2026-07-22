"""Collection diagnostics for the Raw News Collection stage.

Scans every record in data/raw/news/records/ plus the search log and
produces news_collection/collection_diagnostics.json - the numbers the
Raw News Collection Report cites.  Also re-validates every stored
record against raw_news_schema.json (schema validation report), so the
committed diagnostics prove the corpus's structural integrity without
committing the corpus itself.

Purely descriptive: counts and completeness rates only.  No eligibility,
no date resolution, no deduplication happens here.

Usage:
    python3 -m src.news_collection.make_collection_report
"""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from jsonschema import Draft7Validator

RECORDS = Path("data/raw/news/records")
QUARANTINE = Path("data/raw/news/quarantine")
LOG = Path("news_collection/search_log.csv")
OUT = Path("news_collection/collection_diagnostics.json")
VALIDATOR = Draft7Validator(
    json.loads(Path("news_protocol/raw_news_schema.json").read_text()))


def main():
    diag = {
        "generated": "2026-07-22",
        "records_total": 0,
        "schema_invalid": 0,
        "quarantined": len(list(QUARANTINE.glob("*.json"))
                           if QUARANTINE.exists() else []),
        "by_election": Counter(),
        "by_source": Counter(),
        "by_route": Counter(),
        "by_retrieval_status": Counter(),
        "by_date_confidence": Counter(),
        "date_conflicts_flagged": 0,       # Uncertain + conflict note
        "needs_date_review": 0,            # any downstream-review flag
        "metadata_completeness": defaultdict(int),
        "election_x_source": defaultdict(Counter),
    }

    for path in sorted(RECORDS.glob("*.json")):
        rec = json.loads(path.read_text())
        diag["records_total"] += 1
        if next(VALIDATOR.iter_errors(rec), None) is not None:
            diag["schema_invalid"] += 1
        eid = rec["discovered_for_election"]
        src = rec["source_id"]
        diag["by_election"][eid] += 1
        diag["by_source"][src] += 1
        diag["election_x_source"][eid][src] += 1
        diag["by_route"][rec["retrieval"]["access_route"]] += 1
        diag["by_retrieval_status"][rec["retrieval"]["retrieval_status"]] += 1
        diag["by_date_confidence"][rec["dates"]["date_confidence"]] += 1
        note = rec.get("notes") or ""
        if "conflicting publication dates" in note:
            diag["date_conflicts_flagged"] += 1
        if "date review required" in note:
            diag["needs_date_review"] += 1
        for field, present in [
                ("headline", bool(rec["identity"]["headline"])),
                ("byline", bool(rec["identity"]["byline"])),
                ("published_date", bool(rec["dates"]["published_date"])),
                ("date_evidence", bool(rec["dates"]["date_evidence"])),
                ("full_text", rec["content"]["has_full_text"]),
                ("text_sha256", bool(rec["content"]["text_sha256"]))]:
            if present:
                diag["metadata_completeness"][field] += 1

    # search-log side: executed queries, zero-result and failed searches
    log_rows = list(csv.DictReader(LOG.open())) if LOG.exists() else []
    diag["searches_executed"] = len(log_rows)
    diag["searches_zero_result"] = sum(
        1 for r in log_rows if r["results_returned"] == "0")
    diag["search_fetch_failures"] = sum(
        int(r["fetch_failures"] or 0) for r in log_rows)
    diag["queries_by_stage_executed"] = dict(Counter(
        r["query_id"].split("-")[1] if False else "n/a" for r in []))
    inv = list(csv.DictReader(
        open("news_collection/query_inventory.csv")))
    done = {r["query_id"] for r in log_rows}
    diag["inventory_total"] = len(inv)
    diag["inventory_executed"] = len(done)
    diag["inventory_pending_by_stage"] = dict(Counter(
        q["stage"] for q in inv if q["query_id"] not in done))

    # Counters -> plain dicts for JSON
    for k, v in list(diag.items()):
        if isinstance(v, Counter):
            diag[k] = dict(v.most_common())
        elif isinstance(v, defaultdict):
            diag[k] = {a: (dict(b.most_common())
                           if isinstance(b, Counter) else b)
                       for a, b in v.items()}
    OUT.write_text(json.dumps(diag, indent=2))
    print(json.dumps({k: diag[k] for k in
                      ("records_total", "schema_invalid", "quarantined",
                       "by_election", "by_retrieval_status",
                       "by_date_confidence", "date_conflicts_flagged",
                       "needs_date_review", "searches_executed",
                       "searches_zero_result", "inventory_executed",
                       "inventory_pending_by_stage")}, indent=1))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
