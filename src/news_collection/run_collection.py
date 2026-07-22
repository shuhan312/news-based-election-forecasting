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
"""

import argparse

from .runner import load_inventory, run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True,
                    choices=["A", "B", "C", "D", "M"])
    ap.add_argument("--budget", type=int, default=400,
                    help="max article fetches this run (resumable)")
    ap.add_argument("--per-query-cap", type=int, default=None,
                    help="max fetches per query (shallow staged passes)")
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
        from pathlib import Path
        if not Path("news_protocol/division_sample.md").exists():
            return
    if args.stage == "M":
        print("Stage M executes human-completed worksheets; ensure the "
              "worksheet paths in the inventory exist before running.")

    print(f"stage {args.stage}: {len(queries)} queries")
    stats = run(queries, fetch_budget=args.budget,
                per_query_fetch_cap=args.per_query_cap,
                dry_run=args.dry_run)
    print(stats)


if __name__ == "__main__":
    main()
