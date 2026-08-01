"""Run the frozen three-layer extraction over by-election includes.

    python3 -m src.llm_extraction.run_byelection_extraction census
    python3 -m src.llm_extraction.run_byelection_extraction submit byelection1
    python3 -m src.llm_extraction.run_byelection_extraction collect byelection1

Same adaptation discipline as the eligibility wrapper: every prompt,
validator, model assignment (issues on Sonnet, the revised stance and
framing layers on Haiku), retry rule and manifest convention is
``run_corpus_extraction``'s frozen code. This wrapper changes what a
principal-election run must not see changed:

- the decisions and effective-dates inputs point at the by-election
  files, so the tranche frame is exactly the assembled include set;
- the eight pre-holdout by-elections join ``POLLING`` so the window
  assigner can place their articles (the frozen module deliberately
  drops elections it does not know — that was the 2026-07-30 scope
  decision this enrichment revisits);
- the principal pilot/validation sheets are pointed at an empty stream:
  their include lists belong to the principal corpus and would only add
  census noise here.

Tranche names must start with ``byelection`` so none of the
narrow/far/all sampling rules apply: the frame is already exactly the
by-election include set. By-election articles are not in the provisional
normalised-text layer, so every article rides the documented raw-text
fallback, which the manifest records per tranche.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction import run_corpus_extraction as frozen
from src.news_collection.run_byelection_stages import BYELECTION_POLLING_DAYS

frozen.DECISIONS = Path("news_collection/byelection_eligibility_decisions.csv")
frozen.EFFECTIVE_DATES = Path("news_collection/byelection_effective_dates_v1.csv")
frozen.PILOT_SHEET = Path("/dev/null")
frozen.VALIDATION_SHEET = Path("/dev/null")
frozen.POLLING.update(BYELECTION_POLLING_DAYS)

HOLDOUT_DATE = date(2026, 5, 7)


def main() -> None:
    load_dotenv()
    command = sys.argv[1]
    # Belt and braces: the stage-1 registry already refuses holdout-period
    # by-elections, but this wrapper re-checks because it is the one that
    # spends money on what the registry admitted.
    for election_id, polling_day in BYELECTION_POLLING_DAYS.items():
        if polling_day >= HOLDOUT_DATE:
            raise RuntimeError(f"{election_id} is inside the holdout period")

    if command == "census":
        arts, fallback, census = frozen.load_tranche("byelection1")
        print(f"articles in tranche : {len(arts)}")
        print(f"raw-text fallback   : {len(fallback)}")
        print(f"census              : {census}")
        return

    tranche = sys.argv[2]
    if not tranche.startswith("byelection"):
        raise RuntimeError(
            "by-election tranches must be named byelection* so no "
            "principal sampling rule applies")
    sync = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else set()
    if command == "collect":
        frozen.cmd_collect(tranche, sync_layers=sync)
    else:
        {"submit": frozen.cmd_submit}[command](tranche)


if __name__ == "__main__":
    main()
