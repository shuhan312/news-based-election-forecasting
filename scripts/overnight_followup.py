"""Wait for the collection run, retry what never reached the engine, re-measure.

Three jobs, in order:

1. Wait for ``overnight_by_election_collection.py`` to finish.

2. Re-run stage F. Seventy-eight of its 166 searches died on a connection
   reset or DNS failure - a rate-limit signature, since the same key returned
   200 on the other 88 - and the runner checkpointed them anyway, so four
   whole by-elections read as "no coverage" when the truth was "never asked".
   The checkpoint entries have been reopened and the runner now only
   checkpoints searches that reached the engine, so this pass retries exactly
   those. Serper calls are now spaced two seconds apart.

3. Re-run the residual feasibility diagnosis, so the morning report says what
   the join supports now rather than what it supported yesterday.

Step 3 will very likely still report the same candidate-row count. New raw
articles do not become model features until the downstream pipeline runs, and
that pipeline includes LLM extraction, which costs money and has not been
authorised. Running it anyway is the one thing this script must not do.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOG = REPO / "news_collection" / "overnight_run.log"
ROUND_BUDGET = 1500
MAX_ROUNDS = 20


def note(message: str) -> None:
    line = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}  [followup] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def collection_running() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", "overnight_by_election_collection"],
        capture_output=True, text=True, check=False,
    )
    return bool(result.stdout.strip())


def main() -> None:
    note("waiting for the main collection run to finish")
    waited = 0
    while collection_running() and waited < 6 * 3600:
        time.sleep(60)
        waited += 60
    note(f"main run finished (waited {waited // 60} min)")

    note("stage F retry: reopened searches that never reached the engine")
    for round_number in range(1, MAX_ROUNDS + 1):
        result = subprocess.run(
            [sys.executable, "-m", "src.news_collection.run_collection",
             "--stage", "F", "--budget", str(ROUND_BUDGET)],
            cwd=REPO, capture_output=True, text=True, check=False,
        )
        output = (result.stdout or "") + (result.stderr or "")
        tail = output.strip().splitlines()[-1:] if output.strip() else ["(no output)"]
        note(f"retry round {round_number}: {tail[0][:160]}")
        if "'queries_run': 0" in output:
            break

    # Stage C: ward-level CDX across all seven local publishers, for the 17
    # sampled divisions in all four principal elections. This is the change
    # that targets the twenty-row problem directly - 2021 is where those rows
    # come from, and its ward-level archive search previously ran against one
    # publisher out of seven.
    note("stage C: ward-level CDX across all local publishers")
    for round_number in range(1, MAX_ROUNDS + 1):
        result = subprocess.run(
            [sys.executable, "-m", "src.news_collection.run_collection",
             "--stage", "C", "--budget", str(ROUND_BUDGET)],
            cwd=REPO, capture_output=True, text=True, check=False,
        )
        output = (result.stdout or "") + (result.stderr or "")
        tail = output.strip().splitlines()[-1:] if output.strip() else ["(no output)"]
        note(f"stage C round {round_number}: {tail[0][:160]}")
        if "'queries_run': 0" in output:
            break

    note("re-running the residual feasibility diagnosis")
    result = subprocess.run(
        [sys.executable, "-m", "news_modelling.run_residual_feasibility"],
        cwd=REPO, capture_output=True, text=True, check=False,
        env={**__import__("os").environ, "PYTHONPATH": str(REPO / "src")},
    )
    for line in (result.stdout or "").strip().splitlines():
        note(f"  {line}")
    if result.returncode != 0:
        note(f"  diagnosis exited {result.returncode}: "
             f"{(result.stderr or '')[-300:]}")

    note("follow-up complete")


if __name__ == "__main__":
    main()
