"""Extract ONLY the newly admitted local articles (v3 exploratory).

    python3 -m src.llm_extraction.run_e5_backlog_v3_extraction census
    python3 -m src.llm_extraction.run_e5_backlog_v3_extraction submit e5local1
    python3 -m src.llm_extraction.run_e5_backlog_v3_extraction collect e5local1

Same frozen extraction machinery, prompts and model assignment as
every other run. The one thing this wrapper adds is a strict frame:
the tranche is pinned, via ``load_tranche``'s own ``only_ids``
parameter, to the set difference "v3 includes minus v2 includes" - the
articles the reviewer's opening pass newly admitted, and nothing else.

Why the pin matters twice over: re-extracting the 600-plus already-
extracted by-election articles would waste a batch AND could produce
records that differ from the ones the frozen v2 features were built
from - the feature loader's newest-tranche-wins rule would then let a
casual rerun quietly perturb a sealed lineage. Framing the difference
set makes that impossible: old articles never enter this tranche.

The v2 decisions file is read purely as the reference for "already
included"; it is not modified. The probe's post-unblinding guard
applies here too: this wrapper refuses to run before the one-time
unblinding record exists on disk.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction import run_corpus_extraction as frozen
from src.news_collection.run_byelection_stages import BYELECTION_POLLING_DAYS

V2_DECISIONS = Path("news_collection/byelection_eligibility_decisions.csv")
V3_DECISIONS = Path(
    "news_collection/e5_local_backlog_v3/byelection_eligibility_decisions_v3.csv")
UNBLINDING = Path("news_features/unblinding_2026_v1/unblinding_results.json")

frozen.DECISIONS = V3_DECISIONS
frozen.EFFECTIVE_DATES = Path(
    "news_collection/byelection_effective_dates_v1.csv")
frozen.PILOT_SHEET = Path("/dev/null")
frozen.VALIDATION_SHEET = Path("/dev/null")
frozen.POLLING.update(BYELECTION_POLLING_DAYS)


def _includes(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["article_id"] for row in csv.DictReader(handle)
                if row.get("overall_decision") == "include"}


def new_include_ids() -> set[str]:
    new = _includes(V3_DECISIONS) - _includes(V2_DECISIONS)
    if not new:
        raise RuntimeError("no newly included articles - nothing to extract")
    return new


def main() -> None:
    load_dotenv("/Users/sl1425/irp-sl1425/.env")
    if not UNBLINDING.exists():
        raise RuntimeError("v3 extraction may only run after the one-time "
                           "unblinding; record not found")
    command = sys.argv[1]

    new_ids = new_include_ids()
    print(f"frame: {len(new_ids)} newly included local articles")
    # Pin the frame: every call the frozen commands make to
    # load_tranche resolves to exactly the new-include set.
    original_load = frozen.load_tranche
    frozen.load_tranche = (
        lambda tranche, only_ids=None: original_load(tranche,
                                                     only_ids=new_ids))

    if command == "census":
        arts, fallback, census = frozen.load_tranche("e5local1")
        print(f"articles in tranche : {len(arts)}")
        print(f"raw-text fallback   : {len(fallback)}")
        print(f"census              : {census}")
        return

    tranche = sys.argv[2]
    if not tranche.startswith("e5local"):
        raise RuntimeError("v3 tranches must be named e5local* so no "
                           "principal sampling rule applies")
    sync = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else set()
    if command == "collect":
        frozen.cmd_collect(tranche, sync_layers=sync)
    else:
        {"submit": frozen.cmd_submit}[command](tranche)


if __name__ == "__main__":
    main()
