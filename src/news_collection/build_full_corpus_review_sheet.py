"""Build the review sheet for the remaining corpus - every
pending_human_review record that was in neither the 168-article pilot
nor the 128-article validation sample (2,370 records).

This one sheet serves both halves of the §8.5 consequence:

* **The human half (E5).** E5 failed validation, so its column is
  filled by the human reviewer for every row. The sheet carries the
  same reading aids as the pilot/validation sheets (headline, excerpt,
  full-text path, day index) so the reviewer never leaves the file.
* **The machine half (E4/E8, and E6 on Reform-flagged rows).** These
  passed validation, so run_llm_corpus_batch_v2.py reads this same
  sheet to build the frozen-v2 batch requests. Keeping one sheet as
  the single source of the corpus population means the human and the
  model are, verifiably, working through the same article list.

Provenance stays separate by construction: the human types only into
the e5_* columns of this sheet; the LLM's decisions live in
manual_review_llm_v2_corpus.csv keyed by article_id. Nothing merges
them silently - a later, explicit assembly step will, with a
per-decision source label.

Usage:
    python3 -m src.news_collection.build_full_corpus_review_sheet
"""

import csv
from pathlib import Path

from .build_manual_review_sample import (
    build_review_row,
    load_effective_dates,
    load_pool,
    write_csv,
)

PILOT_SAMPLE = Path("news_collection/manual_review_sample.csv")
VALIDATION_SAMPLE = Path("news_collection/llm_validation_sample.csv")
OUT = Path("news_collection/full_corpus_review.csv")


def load_seen_ids() -> set[str]:
    """Every article a human has already reviewed (pilot) or coded as
    the validation gold standard. Membership is read from the sheets
    on disk - the authoritative record - not re-derived from the
    samplers, so this cannot silently disagree with what happened."""
    seen: set[str] = set()
    for path in (PILOT_SAMPLE, VALIDATION_SAMPLE):
        seen.update(r["article_id"] for r in csv.DictReader(path.open()))
    return seen


def main() -> None:
    seen = load_seen_ids()
    # No sampling here - the full-corpus stage reviews EVERYTHING that
    # remains, so the "sample" is simply the untouched population,
    # sorted by article_id for a stable, reproducible sheet.
    pool = [r for r in load_pool() if r["article_id"] not in seen]
    eff_date_by_id = load_effective_dates()

    rows = [
        build_review_row(
            r,
            stratum_tags=f"{r['election_id']}:{r['arm']}"
            + ("|reform" if r["needs_reform_disambiguation"] == "yes" else ""),
            review_round="full_corpus",
            eff_date_by_id=eff_date_by_id,
        )
        for r in pool
    ]
    write_csv(OUT, rows)

    reform = sum(1 for r in pool
                 if r["needs_reform_disambiguation"] == "yes")
    print(f"{len(rows)} remaining-corpus rows -> {OUT} "
          f"({len(seen)} pilot/validation articles excluded, "
          f"{reform} Reform-flagged)")
    print("\nHuman task on this sheet: fill e5_decision / e5_reason_code / "
          "e5_supporting_text / e5_confidence per the codebook. Leave "
          "e4/e6/e8 blank - those come from the validated frozen v2 via "
          "run_llm_corpus_batch_v2.py and are never typed into this file.")


if __name__ == "__main__":
    main()
