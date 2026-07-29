"""Collect in value order rather than stage order.

Stages group queries by election and by how quota-bound a route is. They do
not group by how much a query is worth, and the two orderings are very
different here.

Measured 29 July 2026:

* ``ward_cdx`` is the only family that reliably locates an article to a
  division. The search-engine tier retrieved 700 articles, of which 10 came
  from a Surrey local publisher; the Wayback CDX route has written 6,981
  records across the four principal elections.
* Wayback enforces a six-second pause per fetch, so CDX queries take about
  two minutes each and everything else takes seconds. 93 per cent of the
  remaining collection time is CDX.

Running stages in order therefore put the 445 queries that decide the
division-level row count behind roughly fifteen hours of national context
queries. This runs them in the order they matter:

    1. ward_cdx for 2021 and the ten by-elections Reform contested
       - 2021 is where the current twenty joinable rows come from, and the
         by-elections are where Reform's pre-2026 record is
    2. ward_cdx for the remaining elections
    3. the cheap tiers - Guardian API, publisher site search, Serper
    4. county_cdx, which is Surrey-wide context rather than ward-level

Each step is resumable and a failure in one does not stop the next.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOG = REPO / "news_collection" / "overnight_run.log"
ROUND_BUDGET = 1200
MAX_ROUNDS = 60

# (label, stage, family, election filter)
PLAN: list[tuple[str, str, str | None, str | None]] = [
    ("ward archive - 2021",            "C", "ward_cdx", "SCC-2021-05"),
    ("ward archive - by-elections",    "E", "ward_cdx", None),
    ("ward archive - 2026",            "C", "ward_cdx", "ESWS-2026-05"),
    ("ward archive - 2017",            "C", "ward_cdx", "SCC-2017-05"),
    ("ward archive - 2013",            "C", "ward_cdx", "SCC-2013-05"),
    ("ward archive - other by-elec",   "G", "ward_cdx", None),
    ("search engine - by-elections",   "F", None,       None),
    ("guardian + site search - by-el", "E", None,       None),
    ("county archive - by-elections",  "G", None,       None),
    ("search engine - remaining",      "H", None,       None),
]


def note(message: str) -> None:
    line = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}  [ward-first] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def records() -> int:
    return len(list((REPO / "data" / "raw" / "news" / "records").glob("*.json")))


def run_step(label: str, stage: str, family: str | None,
             election: str | None) -> dict:
    note(f"{label}: starting (stage {stage}"
         f"{', family ' + family if family else ''}"
         f"{', election ' + election if election else ''})")
    before = records()
    totals = {"queries_run": 0, "written": 0}

    for round_number in range(1, MAX_ROUNDS + 1):
        command = [sys.executable, "-m", "src.news_collection.run_collection",
                   "--stage", stage, "--budget", str(ROUND_BUDGET)]
        if family:
            command += ["--family", family]
        if election:
            command += ["--election-contains", election]

        result = subprocess.run(command, cwd=REPO, capture_output=True,
                                text=True, check=False)
        output = (result.stdout or "") + (result.stderr or "")
        if "'queries_run': 0" in output:
            break
        tail = [ln for ln in output.strip().splitlines() if "queries_run" in ln]
        note(f"{label}: round {round_number} {tail[-1][:120] if tail else output.strip()[-120:]}")
        if result.returncode != 0 and not tail:
            note(f"{label}: exited {result.returncode}")
            break

    added = records() - before
    note(f"{label}: done, {added} new record files")
    return {"records_added": added, **totals}


def main() -> None:
    note("=" * 60)
    note("value-ordered collection starting")
    start = records()
    summary = {}
    for label, stage, family, election in PLAN:
        try:
            summary[label] = run_step(label, stage, family, election)
        except Exception as error:  # noqa: BLE001
            note(f"{label}: aborted {error!r}")
            summary[label] = {"error": str(error)}
        (REPO / "news_collection" / "ward_first_summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    note(f"finished. {records() - start} new record files total")


if __name__ == "__main__":
    main()
