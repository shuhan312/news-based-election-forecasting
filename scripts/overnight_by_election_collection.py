"""Run the by-election collection stages to completion, unattended.

Ordered by what unblocks the research question rather than by stage letter:

    F   ward-tier searches for the ten by-elections Reform UK contested.
        These are the only queries that can locate an article to a specific
        division, and division-level attachment is what the residual model's
        row count depends on. 166 queries on Serper, well inside the ~1,169
        free credits remaining.

    E   national and county tier for the same ten contests. Under the
        supervisor's original design the national arm is a first-class part
        of the model - it is what identifies a party's momentum, while the
        local arm identifies which wards convert it - so this is not filler.

    H   ward tier for the nine by-elections Reform did not contest.
    G   national and county tier for those nine.

        Both add candidate rows to the residual model without adding Reform
        rows, so they run last.

Each stage is resumable: run_collection checkpoints completed queries, so a
stage is looped with a fixed fetch budget until a round executes no new
queries. A stage that fails is logged and the next one still runs, because
losing stage G should not cost stage F's results.

Nothing here costs money. Guardian and Wayback are free, Serper draws on
credits already bought, and no LLM extraction is triggered - that step is
gated on a budget the operator has not been asked for.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOG = REPO / "news_collection" / "overnight_run.log"
SUMMARY = REPO / "news_collection" / "overnight_run_summary.json"
SEARCH_LOG = REPO / "news_collection" / "search_log.csv"

# Fetch budget per round. Small enough that a stalled fetch cannot burn the
# whole night on one query, large enough that a round makes real progress.
ROUND_BUDGET = 1500

# Rounds per stage before giving up. A stage that still reports new queries
# after this many rounds is logged as incomplete rather than looped forever.
MAX_ROUNDS = 40

STAGES = ["F", "E", "H", "G"]


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def note(message: str) -> None:
    line = f"{stamp()}  {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def record_count() -> int:
    """Raw article records on disk, as a progress signal independent of the log."""

    return len(list((REPO / "data" / "raw" / "news" / "records").glob("*.json")))


def run_round(stage: str) -> dict:
    """One resumable pass over a stage. Returns the runner's own tallies."""

    result = subprocess.run(
        [sys.executable, "-m", "src.news_collection.run_collection",
         "--stage", stage, "--budget", str(ROUND_BUDGET)],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")

    # The runner prints a dict of tallies as its last line. Parsed rather than
    # inferred from the log, so a round that wrote nothing is distinguishable
    # from a round that never ran.
    tallies = {}
    for match in re.finditer(r"\{'queries_run'.*?\}", output):
        try:
            tallies = json.loads(match.group(0).replace("'", '"'))
        except json.JSONDecodeError:
            pass
    return {
        "returncode": result.returncode,
        "tallies": tallies,
        "tail": output.strip().splitlines()[-3:] if output.strip() else [],
    }


def run_stage(stage: str) -> dict:
    """Loop a stage until a round executes no new queries."""

    note(f"stage {stage}: starting")
    before = record_count()
    rounds = 0
    totals = {"queries_run": 0, "written": 0, "existing": 0, "failures": 0}
    status = "complete"

    for rounds in range(1, MAX_ROUNDS + 1):
        outcome = run_round(stage)
        tallies = outcome["tallies"]

        if outcome["returncode"] != 0 and not tallies:
            note(f"stage {stage}: round {rounds} failed "
                 f"(exit {outcome['returncode']}) {outcome['tail']}")
            status = "failed"
            break

        for key in totals:
            totals[key] += int(tallies.get(key, 0) or 0)

        note(f"stage {stage}: round {rounds} "
             f"queries={tallies.get('queries_run', 0)} "
             f"written={tallies.get('written', 0)} "
             f"existing={tallies.get('existing', 0)} "
             f"failures={tallies.get('failures', 0)}")

        # No new queries executed means the stage's checkpoint is complete.
        if not int(tallies.get("queries_run", 0) or 0):
            break
    else:
        status = "incomplete_round_limit"
        note(f"stage {stage}: still had work after {MAX_ROUNDS} rounds")

    after = record_count()
    note(f"stage {stage}: {status} after {rounds} round(s), "
         f"{after - before} new record files")
    return {"status": status, "rounds": rounds,
            "records_added": after - before, **totals}


def main() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    note("=" * 62)
    note("overnight by-election collection starting")
    started_records = record_count()
    note(f"raw record files on disk at start: {started_records}")

    summary = {"started": stamp(), "records_at_start": started_records,
               "stages": {}}

    for stage in STAGES:
        try:
            summary["stages"][stage] = run_stage(stage)
        except Exception as error:  # noqa: BLE001 - one stage must not end the run
            note(f"stage {stage}: aborted with {error!r}")
            summary["stages"][stage] = {"status": "exception",
                                        "error": str(error)}
        SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    summary["finished"] = stamp()
    summary["records_at_end"] = record_count()
    summary["records_added"] = summary["records_at_end"] - started_records
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    note(f"finished. {summary['records_added']} new record files "
         f"({started_records} -> {summary['records_at_end']})")
    note("=" * 62)


if __name__ == "__main__":
    main()
