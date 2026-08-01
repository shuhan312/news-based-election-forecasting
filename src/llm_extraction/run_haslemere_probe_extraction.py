"""Run the frozen three-layer extraction over the Haslemere probe includes.

    python3 -m src.llm_extraction.run_haslemere_probe_extraction census
    python3 -m src.llm_extraction.run_haslemere_probe_extraction submit haslemere1
    python3 -m src.llm_extraction.run_haslemere_probe_extraction collect haslemere1

Same adaptation discipline as the enrichment wrapper: prompts,
validators, model assignment (issues on Sonnet, revised stance and
framing on Haiku), retry rules and manifest conventions are
``run_corpus_extraction``'s frozen code. Only the file frame changes:
decisions and effective dates point at the probe's assembled 20-article
include set, the pilot/validation sheets are silenced, and the one
probe election joins ``POLLING`` so the window assigner can place its
articles.

The enrichment wrapper refuses holdout-period elections because its
output feeds training. This probe inverts the guard: it may run ONLY
after the one-time unblinding record exists on disk, because its whole
legitimacy rests on being post-confirmatory - the frozen models will
predict the contest, nothing will be fitted, and no confirmatory
surface remains for these articles to contaminate. Tranche names must
start with ``haslemere`` (not ``far``), so no principal sampling rule
applies and the frame is exactly the include set.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction import run_corpus_extraction as frozen

HASLEMERE = "surrey-county-council-by-election-haslemere-2026-07-07"
UNBLINDING = Path("news_features/unblinding_2026_v1/unblinding_results.json")

frozen.DECISIONS = Path(
    "news_collection/haslemere_probe/eligibility_decisions.csv")
frozen.EFFECTIVE_DATES = Path(
    "news_collection/haslemere_probe/effective_dates.csv")
frozen.PILOT_SHEET = Path("/dev/null")
frozen.VALIDATION_SHEET = Path("/dev/null")
frozen.POLLING.update({HASLEMERE: date(2026, 7, 7)})


def main() -> None:
    load_dotenv("/Users/sl1425/irp-sl1425/.env")
    command = sys.argv[1]
    # The probe's legitimacy precondition, machine-checked before any
    # money is spent: the one-time unblinding must already be on disk.
    if not UNBLINDING.exists():
        raise RuntimeError(
            "the Haslemere probe may only run after the one-time 2026 "
            f"unblinding; {UNBLINDING} not found")

    if command == "census":
        arts, fallback, census = frozen.load_tranche("haslemere1")
        print(f"articles in tranche : {len(arts)}")
        print(f"raw-text fallback   : {len(fallback)}")
        print(f"census              : {census}")
        return

    tranche = sys.argv[2]
    if not tranche.startswith("haslemere"):
        raise RuntimeError(
            "probe tranches must be named haslemere* so no principal "
            "sampling rule applies")
    sync = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else set()
    if command == "collect":
        frozen.cmd_collect(tranche, sync_layers=sync)
    else:
        {"submit": frozen.cmd_submit}[command](tranche)


if __name__ == "__main__":
    main()
