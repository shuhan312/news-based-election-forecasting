"""Readiness gate for the Raw News Corpus Construction phase.

The pipeline's own design (source_adapter_framework.md) already gates
Stage C on the division sample existing (run_collection.py refuses to
run it otherwise). This script is the matching gate at the OTHER end:
before the project moves on to the next stage (Publication Date
Resolution), it should be possible to state precisely - not from
memory or a feeling of "we've done a lot" - which parts of the query
inventory have actually been executed and which have not, stage by
stage, and query index cross-referenced against the search log itself
so we do not have to trust a printed summary from whenever a stage was
last run.

This deliberately does NOT decide "done" for you. Stage M is expected
to stay incomplete until GOOGLE_CSE_API_KEY/GOOGLE_CSE_ENGINE_ID are
configured - that is a documented, external dependency, not a defect.
The script reports readiness per stage and lets the reader judge
whether the corpus is ready to hand off, exactly the same "log the
gap, do not silently decide" discipline used everywhere else in this
project.

Usage:
    python3 -m src.news_collection.check_completeness
"""

import csv
import json
from collections import Counter
from pathlib import Path

INVENTORY = Path("news_collection/query_inventory.csv")
LOG = Path("news_collection/search_log.csv")
OUT = Path("news_collection/completeness_check.json")

# What "automated and therefore expected to reach 100%" means per
# stage, so the report can flag a stage as HELD_BACK (blocked on
# something external) rather than lumping every incomplete stage
# together as equally concerning.
STAGE_NOTES = {
    "A": "Guardian API - fully automated, no external blocker",
    "B": "local publisher first pass - fully automated, no external blocker",
    "C": "ward-tier CDX (17 sampled divisions) - fully automated, no external blocker",
    "D": "bulk county-tier CDX - fully automated, no external blocker",
    "M": "ward-tier Google search - requires GOOGLE_CSE_API_KEY/"
        "GOOGLE_CSE_ENGINE_ID (proposal P3, pending supervisor "
        "confirmation); incompleteness here is an external dependency, "
        "not a defect",
}


def main():
    inventory_ids = {
        r["query_id"]: r["stage"]
        for r in csv.DictReader(INVENTORY.open())
    }
    executed_ids = ({r["query_id"] for r in csv.DictReader(LOG.open())}
                    if LOG.exists() else set())

    by_stage_total = Counter(inventory_ids.values())
    by_stage_done = Counter(
        stage for qid, stage in inventory_ids.items() if qid in executed_ids)

    report = {"stages": {}}
    for stage in sorted(by_stage_total):
        total = by_stage_total[stage]
        done = by_stage_done.get(stage, 0)
        pending = total - done
        report["stages"][stage] = {
            "total_queries": total, "executed": done, "pending": pending,
            "percent_complete": round(100 * done / total, 1) if total else 0,
            "note": STAGE_NOTES.get(stage, ""),
        }

    # A stage counts as "automation-complete" only if every one of its
    # queries has actually run - not just "most of it" - since a
    # missed query is silent under-coverage otherwise.
    automated_stages = [s for s in ("A", "B", "C", "D") if s in report["stages"]]
    automation_complete = all(
        report["stages"][s]["pending"] == 0 for s in automated_stages)
    report["automation_complete"] = automation_complete
    report["ready_for_next_pipeline_stage"] = automation_complete
    report["blocking_stage_M_on_external_credentials"] = (
        report["stages"].get("M", {}).get("pending", 0) > 0)

    OUT.write_text(json.dumps(report, indent=2))

    print("Raw News Corpus Construction - completeness by stage")
    print("-" * 60)
    for stage, d in report["stages"].items():
        flag = "OK" if d["pending"] == 0 else (
            "BLOCKED (external)" if stage == "M" else "INCOMPLETE")
        print(f"  {stage}: {d['executed']}/{d['total_queries']} "
              f"({d['percent_complete']}%) [{flag}]")
    print("-" * 60)
    if automation_complete:
        print("All automated stages (A-D) fully executed. Stage M remains "
              "gated on Google credentials only - the phase is ready to "
              "hand off to Publication Date Resolution.")
    else:
        incomplete = [s for s in automated_stages
                     if report["stages"][s]["pending"] > 0]
        print(f"NOT YET READY: automated stage(s) {incomplete} still have "
              "pending queries - run them before treating Raw News Corpus "
              "Construction as complete.")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
