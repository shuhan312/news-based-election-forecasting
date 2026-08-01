"""Frozen v2 eligibility batch over the Haslemere probe sheet.

    python3 -m src.news_collection.run_haslemere_probe_llm_batch submit
    python3 -m src.news_collection.run_haslemere_probe_llm_batch collect
    python3 -m src.news_collection.run_haslemere_probe_llm_batch retry

Same four-line adaptation as the enrichment wrapper, for the same
reason: the classifier prompt, schema, request shape, merge rule and
raw-response archive are the frozen module's own, still guarded by
``assert_classifier_frozen``; only the file paths change, so this batch
cannot touch the principal or enrichment sheets, outputs or state.

Scope per the production protocol: the model answers E4 and E8 for
every row (E6 would apply to Reform-flagged rows; the probe pool has
none). E5 for these all-local rows stays a human judgement - after this
batch is collected, the rows that survive E4/E8 are queued for the
user's E5 pass, and assembly waits for both.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from . import run_llm_corpus_batch_v2 as frozen
from .run_llm_validation_v2 import assert_classifier_frozen

frozen.SHEET = Path("news_collection/haslemere_probe/review_sheet.csv")
frozen.OUT = Path("news_collection/haslemere_probe/llm_v2.csv")
frozen.RAW_RESPONSE_DIR = Path("news_collection/haslemere_probe/llm_v2_raw")
frozen.STATE = Path("news_collection/haslemere_probe/llm_v2_batch_state.json")


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
