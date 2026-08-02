"""Frozen v2 eligibility batch over the Woking South blind-test sheet.

    python3 -m src.news_collection.run_woking_south_blind_llm_batch submit
    python3 -m src.news_collection.run_woking_south_blind_llm_batch collect
    python3 -m src.news_collection.run_woking_south_blind_llm_batch retry

Fourth instance of the four-line adaptation (enrichment, probe, v3,
now the blind test): classifier prompt, schema, request shape, merge
rule and raw-response archive are the frozen module's, guarded by
``assert_classifier_frozen``; only the paths change. Scope per the
production protocol: E4 and E8 for every row, E6 for the 119
Reform-flagged rows; E5 is recorded for audit only - the usable local
E5 is the human's, the usable national E5 is this output's llm column
at assembly. No stage here reads any outcome for the contest.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from . import run_llm_corpus_batch_v2 as frozen
from .run_llm_validation_v2 import assert_classifier_frozen

frozen.SHEET = Path("news_collection/woking_south_blind/review_sheet.csv")
frozen.OUT = Path("news_collection/woking_south_blind/llm_v2.csv")
frozen.RAW_RESPONSE_DIR = Path("news_collection/woking_south_blind/llm_v2_raw")
frozen.STATE = Path("news_collection/woking_south_blind/llm_v2_batch_state.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["submit", "collect", "retry"])
    arguments = parser.parse_args()
    assert_classifier_frozen()
    load_dotenv("/Users/sl1425/irp-sl1425/.env")
    {"submit": frozen.submit, "collect": frozen.collect,
     "retry": frozen.retry}[arguments.command]()


if __name__ == "__main__":
    main()
