"""CLI entry point for staged Raw News Collection.

Stages (assigned in the query inventory, executed in order):
  A  Guardian API - national + county tier, all four elections
  B  local publishers first pass - site search (robots-permitting)
     + bounded SurreyLive CDX batch for the 2026 window
  C  ward-tier CDX discovery (blocked until the division sample for
     supervisor to-do 7 is committed - see collection report)
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
    ap.add_argument("--stage", required=True,
                    choices=["A", "B", "C", "D", "M"])
    ap.add_argument("--budget", type=int, default=400,
                    help="max article fetches this run (resumable)")
    ap.add_argument("--per-query-cap", type=int, default=None,
                    help="max fetches per query (shallow staged passes)")
    ap.add_argument("--max-queries", type=int, default=None,
                    help="max NEW searches (queries) this invocation - "
                        "use this to stay under a search-engine quota "
                        "(Google CSE / SerpAPI); already-completed "
                        "queries do not count")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    queries = [q for q in load_inventory() if q["stage"] == args.stage]
    if args.stage == "C":
        # Hard guard, mirroring the protocol's pre-registration rule:
        # ward-tier collection must not start before the division
        # sampling decision is committed to the repository.
        print("Stage C is gated on the committed division sample "
              "(supervisor to-do 7). Refusing to run until "
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
                dry_run=args.dry_run)
    print(stats)


if __name__ == "__main__":
    main()
