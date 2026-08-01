"""Assemble the by-election eligibility decisions (stage 5).

    python3 -m src.news_collection.run_byelection_assembly

Same four-constant adaptation as the batch wrapper: the merge rules,
per-rule provenance labels, human-over-LLM precedence and the
derive-never-store overall decision are ``assemble_corpus_decisions``'s
frozen code, pointed at the by-election sheet, LLM output, second-review
queue and output file. Safe to re-run after every human E5 tranche and
after every LLM retry collection: rows still missing a required stream
are emitted as pending with a named blocker, never guessed.
"""

from __future__ import annotations

from pathlib import Path

from . import assemble_corpus_decisions as frozen

frozen.SHEETS = (Path("news_collection/byelection_review.csv"),)
frozen.LLM_OUTPUTS = (Path("news_collection/byelection_llm_v2.csv"),)
frozen.QUEUE = Path("news_collection/byelection_second_review_queue.csv")
frozen.OUT = Path("news_collection/byelection_eligibility_decisions.csv")


def main() -> None:
    frozen.main()


if __name__ == "__main__":
    main()
