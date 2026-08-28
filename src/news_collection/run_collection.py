"""CLI entry point for staged Raw News Collection.

Stages (assigned in the query inventory, executed in order):
  A  Guardian API - national + county tier, all four elections
  B  local publishers first pass - site search (robots-permitting)
     + bounded SurreyLive CDX batch for the 2026 window
  C  ward-tier CDX discovery (gated on the committed division sample)
  D  bulk county-tier CDX for remaining sources/windows
  M  manual routes (Google worksheets, archive transcriptions)

Interrupting a run is safe: completed queries are checkpointed and
skipped on the next invocation, and article writes are idempotent.

Usage:
    python3 -m src.news_collection.run_collection --stage A
    python3 -m src.news_collection.run_collection --stage B --budget 120
    python3 -m src.news_collection.run_collection --stage A --dry-run
    python3 -m src.news_collection.run_collection --stage M --max-queries 240

--max-queries exists because search-engine quotas (Google CSE's daily
free tier, a personal SerpAPI plan) are counted in SEARCHES, one per
query, not in article fetches. --budget alone cannot express "stop
after N searches" since a single query can yield anywhere from 0 to
several fetches - --max-queries caps the number of inventory rows
(=searches) attempted in this invocation, so a free-tier quota is
never silently overrun. Already-completed queries (checkpointed) do
not count against this limit, so repeated bounded calls make steady
progress across a large stage like M without ever exceeding a quota
in a single run.
"""

import argparse
from pathlib import Path

from .runner import load_inventory, run


def main():
    ap = argparse.ArgumentParser()
    # A-D, M  principal elections (2013, 2017, 2021, 2026)
    # E, F     by-elections Reform UK contested - the eight training-period
    #          contests holding its pre-2026 record, plus the two 2026
    #          holdout by-elections whose news is needed for prediction
    # G, H     by-elections Reform did not contest
    # F and H are the Google CSE tier, capped at 100 free queries a day.
    ap.add_argument("--stage", required=True,
                    choices=["A", "B", "C", "D", "E", "F", "G", "H", "M", "M2"])
    ap.add_argument("--budget", type=int, default=400,
                    help="max article fetches this run (resumable)")
    ap.add_argument("--per-query-cap", type=int, default=None,
                    help="max fetches per query (shallow staged passes)")
    ap.add_argument("--max-queries", type=int, default=None,
                    help="max NEW searches (queries) this invocation - "
                        "use this to stay under a search-engine quota "
                        "(Google CSE / SerpAPI); already-completed "
                        "queries do not count")
    ap.add_argument("--redo-completed", action="store_true",
                    help="re-execute already-checkpointed queries - "
                         "use to DEEPEN a stage first run with a small "
                         "--per-query-cap, whose remaining hits would "
                         "otherwise stay unfetched forever. Writes are "
                         "idempotent and a re-run appends a new log "
                         "row, so the shallow pass stays auditable")
    # Run one query family across every stage.
    #
    # Stages group queries by which election and how quota-bound they are;
    # they do not group by value. Measured on 29 July 2026, ward_cdx is the
    # only family that reliably locates an article to a division - the search
    # engines returned 700 articles of which 10 came from a Surrey local
    # publisher - and Wayback's six-second politeness pause makes the CDX
    # families the slow ones. Without this, the 445 ward_cdx queries that
    # decide the row count sit behind hours of national context queries.
    ap.add_argument("--family",
                    help="only run this query_family (e.g. ward_cdx)")
    ap.add_argument("--election-contains",
                    help="only run queries whose election_id contains this")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    queries = [q for q in load_inventory() if q["stage"] == args.stage]
    if args.family:
        queries = [q for q in queries if q["query_family"] == args.family]
    if args.election_contains:
        queries = [q for q in queries
                   if args.election_contains in q["election_id"]]
    if args.stage == "C":
        # Hard guard, mirroring the protocol's pre-registration rule:
        # ward-tier collection must not start before the division
        # sampling decision is committed to the repository.
        print("Stage C is gated on the committed division sample "
              "and will not run unless "
              "news_protocol/division_sample.md exists.")
        if not Path("news_protocol/division_sample.md").exists():
            return
    if args.stage == "M":
        print("Stage M runs through an automated search-engine adapter "
              "(serpapi or google_cse) - see adapters.py. Queries whose "
              "adapter has no configured credentials are logged with "
              "the gap, not silently skipped or faked as zero-result.")
    print(f"stage {args.stage}: {len(queries)} queries")
    stats = run(queries, fetch_budget=args.budget,
                per_query_fetch_cap=args.per_query_cap,
                max_new_searches=args.max_queries,
                dry_run=args.dry_run,
                redo_completed=args.redo_completed)
    print(stats)


if __name__ == "__main__":
    main()
