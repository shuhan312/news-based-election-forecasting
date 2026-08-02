"""Frozen three-layer extraction over the Woking South blind includes.

    python3 -m src.llm_extraction.run_woking_south_blind_extraction census
    python3 -m src.llm_extraction.run_woking_south_blind_extraction submit wokingsouth1
    python3 -m src.llm_extraction.run_woking_south_blind_extraction collect wokingsouth1

Same adaptation as the probe's wrapper: prompts, validators, model
assignment (issues on Sonnet, revised stance and framing on Haiku),
retry rules and manifests are ``run_corpus_extraction``'s frozen code;
the file frame points at the blind test's assembled decisions, the
pilot/validation sheets are silenced, and the one election joins
POLLING so the window assigner can place its articles.

Guards, in protocol order: the run refuses to start before the
one-time unblinding record exists (the blind test's legitimacy
precondition), and tranche names must start with ``wokingsouth`` so
no principal sampling rule can apply. Nothing here reads any outcome
column for the contest.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction import run_corpus_extraction as frozen

WOKING_SOUTH = "surrey-county-council-by-election-woking-south-2025-07-10"
UNBLINDING = Path("news_features/unblinding_2026_v1/unblinding_results.json")

frozen.DECISIONS = Path(
    "news_collection/woking_south_blind/eligibility_decisions.csv")
frozen.EFFECTIVE_DATES = Path(
    "news_collection/woking_south_blind/effective_dates.csv")
frozen.PILOT_SHEET = Path("/dev/null")
frozen.VALIDATION_SHEET = Path("/dev/null")
frozen.POLLING.update({WOKING_SOUTH: date(2025, 7, 10)})


def main() -> None:
    load_dotenv("/Users/sl1425/irp-sl1425/.env")
    if not UNBLINDING.exists():
        raise RuntimeError("blind-test extraction may only run after the "
                           "one-time unblinding; record not found")
    command = sys.argv[1]
    if command == "census":
        arts, fallback, census = frozen.load_tranche("wokingsouth1")
        print(f"articles in tranche : {len(arts)}")
        print(f"raw-text fallback   : {len(fallback)}")
        print(f"census              : {census}")
        return
    tranche = sys.argv[2]
    if not tranche.startswith("wokingsouth"):
        raise RuntimeError("blind-test tranches must be named wokingsouth*")
    sync = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else set()
    if command == "collect":
        frozen.cmd_collect(tranche, sync_layers=sync)
    else:
        {"submit": frozen.cmd_submit}[command](tranche)


if __name__ == "__main__":
    main()
