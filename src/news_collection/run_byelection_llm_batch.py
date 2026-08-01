"""Run the frozen v2 eligibility batch over the by-election review sheet.

    python3 -m src.news_collection.run_byelection_llm_batch submit
    python3 -m src.news_collection.run_byelection_llm_batch collect
    python3 -m src.news_collection.run_byelection_llm_batch retry

This is a four-line adaptation, on purpose. Everything that decides what
the model sees and how its answers are judged — the frozen classifier's
prompt and schema builders, the request shape, the ok-rows-are-final
merge rule, the raw-response archive — is ``run_llm_corpus_batch_v2``'s
code, imported unmodified and still guarded by
``assert_classifier_frozen``. The only thing this wrapper changes is
which files the run reads and writes, so the by-election batch can never
touch the principal corpus's sheet, output, raw archive or state file.

Scope is identical to the principal run per §8.5: E4 and E8 for every
row, E6 for Reform-flagged rows; E5 is in the frozen prompt and recorded
for audit but never used downstream — usable local-arm E5 comes from the
human's byelection_review.csv pass, and national-arm E5 from this
output's llm_v2 column at assembly, exactly as the principal decisions
table records it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from . import run_llm_corpus_batch_v2 as frozen
from .run_llm_validation_v2 import assert_classifier_frozen

# The complete adaptation: by-election paths in, principal paths out of
# reach. The frozen module's functions read these globals at call time.
frozen.SHEET = Path("news_collection/byelection_review.csv")
frozen.OUT = Path("news_collection/byelection_llm_v2.csv")
frozen.RAW_RESPONSE_DIR = Path("news_collection/llm_v2_byelection_raw")
frozen.STATE = Path("news_collection/llm_v2_byelection_batch_state.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["submit", "collect", "retry"])
    arguments = parser.parse_args()
    assert_classifier_frozen()
    load_dotenv()
    {"submit": frozen.submit, "collect": frozen.collect,
     "retry": frozen.retry}[arguments.command]()


if __name__ == "__main__":
    main()
