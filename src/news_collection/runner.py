"""CollectionRunner - executes the query inventory against the adapters.

Owns every cross-cutting guarantee of the framework design (section 5):

  * plan execution: only queries from the committed inventory run;
    nothing is queried ad hoc
  * logging: one row per executed query in news_collection/search_log.csv
    (protocol section 5.3 fields), zero-result and failed searches
    logged identically, append-only
  * checkpointing: completed query_ids recorded after each query in
    news_collection/checkpoints/completed_queries.json, so interrupted
    runs resume without repeating searches
  * budgets: a per-run fetch budget stops a misbehaving source from
    consuming quotas; the run simply resumes later
  * persistence: records + sidecars via schema.save_record, which
    validates against raw_news_schema.json and quarantines failures
"""

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()          # GUARDIAN_KEY / NEWSAPI_KEY live in .env

from . import SOFTWARE_VERSION, PROTOCOL_VERSION
from .adapters import (GuardianAdapter, ManualImportAdapter,
                       SiteSearchAdapter, WaybackAdapter)

LOG_PATH = Path("news_collection/search_log.csv")
CHECKPOINT = Path("news_collection/checkpoints/completed_queries.json")

LOG_FIELDS = ["query_id", "election_id", "ward", "arm", "source_id",
              "retrieval_route", "query_text", "window_start", "window_end",
              "executed_at", "ordering", "results_returned",
              "records_written", "records_existing", "records_quarantined",
              "fetch_failures", "search_status", "software_version",
              "protocol_version", "note"]


def load_inventory(path="news_collection/query_inventory.csv"):
    return list(csv.DictReader(open(path)))


def load_checkpoint():
    if CHECKPOINT.exists():
        return set(json.loads(CHECKPOINT.read_text()))
    return set()


def save_checkpoint(done):
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps(sorted(done), indent=0))


def append_log(row):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def make_adapters():
    return {
        "api": GuardianAdapter(os.getenv("GUARDIAN_KEY")),
        "wayback_cdx": WaybackAdapter(),
        "site_search": SiteSearchAdapter(),
        "manual_import": ManualImportAdapter(),
    }


def run(queries, *, fetch_budget=400, per_query_fetch_cap=None,
        dry_run=False):
    """Execute a list of inventory queries (already filtered by the
    caller to the intended stage).  Returns run statistics.

    fetch_budget        hard cap on article fetches for this run
    per_query_fetch_cap optional cap on fetches per query (staged
                        collection: shallow first pass, deepen later -
                        re-running a completed query is a NEW log row,
                        never an edit)
    """
    adapters = make_adapters()
    done = load_checkpoint()
    stats = {"queries_run": 0, "skipped_done": 0, "written": 0,
             "existing": 0, "quarantined": 0, "failures": 0}
    fetches = 0

    for q in queries:
        if q["query_id"] in done:
            stats["skipped_done"] += 1
            continue
        if fetches >= fetch_budget:
            print(f"fetch budget {fetch_budget} reached - run resumable")
            break
        adapter = adapters[q["retrieval_route"]]
        if dry_run:
            print("DRY", q["query_id"], q["query_text"][:60])
            continue

        hits, search_meta = adapter.search(q)
        search_status = (search_meta[-1].get("status")
                         if search_meta else None)
        written = existing = quarantined = failed = 0

        cap = per_query_fetch_cap or len(hits)
        for hit in hits[:cap]:
            if fetches >= fetch_budget:
                break
            fetches += 1
            try:
                record, raw = adapter.fetch(hit, q)
            except Exception as e:                     # noqa: BLE001
                failed += 1
                print(f"    fetch error {q['query_id']}: "
                      f"{e.__class__.__name__}")
                continue
            from .schema import save_record
            status, _ = save_record(record,
                                    text=raw.get("text"),
                                    raw_html=raw.get("raw_html"),
                                    raw_api=raw.get("raw_api"))
            if status == "ok":
                written += 1
            elif status == "exists":
                existing += 1
            else:
                quarantined += 1
            if record["retrieval"]["retrieval_status"] != "ok":
                failed += 1        # blocked/gone/paywalled: kept AND counted

        append_log({
            "query_id": q["query_id"], "election_id": q["election_id"],
            "ward": q.get("ward", ""), "arm": q["arm"],
            "source_id": q["source_id"],
            "retrieval_route": q["retrieval_route"],
            "query_text": q["query_text"],
            "window_start": q["window_start"],
            "window_end": q["window_end"],
            "executed_at": datetime.now(timezone.utc)
                           .isoformat(timespec="seconds"),
            "ordering": "oldest" if q["retrieval_route"] == "api"
                        else "ranked",
            "results_returned": len(hits),
            "records_written": written, "records_existing": existing,
            "records_quarantined": quarantined, "fetch_failures": failed,
            "search_status": search_status,
            "software_version": SOFTWARE_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "note": json.dumps(search_meta)[:300],
        })
        done.add(q["query_id"])
        save_checkpoint(done)          # checkpoint after EVERY query
        stats["queries_run"] += 1
        stats["written"] += written
        stats["existing"] += existing
        stats["quarantined"] += quarantined
        stats["failures"] += failed
        print(f"  {q['query_id']}: hits={len(hits)} written={written} "
              f"existing={existing} failed={failed}")
    return stats
