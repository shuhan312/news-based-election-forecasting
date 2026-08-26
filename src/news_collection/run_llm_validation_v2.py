"""Run the FROZEN v2 classifier once on the 128-article blind
validation sample (eligibility_manual_review_methodology.md §8.4
step 3).

Preconditions, all satisfied before this script was first run
--------------------------------------------------------------
1. §8's amendment (AC1/PABAK fallback gate for prevalence-skewed
   rules) was approved by the supervisor by email on 2026-07-24,
   after being pre-registered the same day.
2. The 128 human rows in llm_validation_sample.csv were fully coded
   and validate_row()-clean BEFORE any v2 output existed for them.
3. v2 is frozen: the FROZEN_* constants below record the exact
   classifier identity this validation is scoring. If anyone edits
   llm_classifier_v2.py afterwards, the assertion fails and the run
   refuses to start - a changed classifier needs a NEW validation
   sample, not a quiet rerun on this one.

Everything else (full-text input, response archiving, reuse only on
identical request hashes, failures stay failures) uses the shared frozen-v2
I/O helpers in llm_v2_io.py, the same helpers as the production corpus runs.

This script only produces classifications. The gated comparison
against the human gold standard lives in
compare_llm_validation_agreement.py.

Usage:
    python3 -m src.news_collection.run_llm_validation_v2
"""

from __future__ import annotations

import csv
from pathlib import Path

from dotenv import load_dotenv

from . import llm_classifier_v2
from .llm_classifier_v2 import classify_article_v2
from .llm_v2_io import (
    FIELDNAMES,
    archive_raw_result,
    article_from_sample_row,
    backup_previous_output,
    can_reuse,
    csv_row,
    load_previous_ok_rows,
    load_query_inventory,
)

VALIDATION_SAMPLE = Path("news_collection/llm_validation_sample.csv")
OUT = Path("news_collection/manual_review_llm_v2_validation.csv")
RAW_RESPONSE_DIR = Path("news_collection/llm_v2_validation_raw")

# The frozen classifier identity. Recorded 2026-07-24, at supervisor
# approval, from the values the development run actually used. The
# per-article prompt/schema hashes are additionally written into every
# output row and archived response, so the freeze is verifiable after
# the fact as well as enforced before it.
FROZEN_CLASSIFIER_VERSION = "v2-development-2026-07-24.6"
FROZEN_MODEL = "claude-sonnet-5"


def assert_classifier_frozen() -> None:
    """Refuse to run if llm_classifier_v2 no longer matches the freeze.

    This is the §8.4 step-1 guarantee in executable form: validation
    results are only meaningful for the exact classifier that was
    frozen before the sample was scored.
    """
    problems = []
    if llm_classifier_v2.CLASSIFIER_VERSION != FROZEN_CLASSIFIER_VERSION:
        problems.append(
            f"CLASSIFIER_VERSION is {llm_classifier_v2.CLASSIFIER_VERSION!r}, "
            f"frozen at {FROZEN_CLASSIFIER_VERSION!r}")
    if llm_classifier_v2.MODEL != FROZEN_MODEL:
        problems.append(
            f"MODEL is {llm_classifier_v2.MODEL!r}, frozen at {FROZEN_MODEL!r}")
    if problems:
        raise RuntimeError(
            "v2 has changed since it was frozen - this validation sample "
            "cannot score the edited classifier (it would need a fresh "
            "sample):\n  " + "\n  ".join(problems))


def main() -> None:
    assert_classifier_frozen()
    load_dotenv()

    with VALIDATION_SAMPLE.open(newline="") as handle:
        sample_rows = [
            row for row in csv.DictReader(handle)
            if row["review_round"] == "llm_validation"
        ]
    if not sample_rows:
        raise RuntimeError(f"no llm_validation rows in {VALIDATION_SAMPLE}")

    query_by_id = load_query_inventory()
    previous_ok = load_previous_ok_rows(OUT)
    backup = backup_previous_output(OUT)
    if backup:
        print(f"previous validation output backed up -> {backup}")

    output_rows = []
    status_counts: dict[str, int] = {}
    reused = attempted = 0
    for sample_row in sample_rows:
        article = article_from_sample_row(sample_row, query_by_id=query_by_id)
        previous = previous_ok.get(sample_row["article_id"])
        if previous and can_reuse(previous, article):
            # Identical request identity -> reuse, so an interrupted run
            # can resume without re-rolling articles that already have a
            # valid answer (selective rerunning is the abuse this blocks).
            output_rows.append(previous)
            status = "ok"
            reused += 1
        else:
            result = classify_article_v2(article)
            archive_raw_result(
                sample_row["article_id"], result, directory=RAW_RESPONSE_DIR)
            output_rows.append(csv_row(sample_row, article, result))
            status = result.get("status", "unknown")
            attempted += 1
        status_counts[status] = status_counts.get(status, 0) + 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"{len(output_rows)} validation rows -> {OUT}")
    print(f"{reused} reused; {attempted} attempted")
    print("by status:", status_counts)
    print("\nNext: python3 -m src.news_collection."
          "compare_llm_validation_agreement")


if __name__ == "__main__":
    main()
