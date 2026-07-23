"""Take a partially hand-filled review sheet (manual_review_sample.csv
or manual_review_kappa_subset.csv) and do the two things a reviewer
should never have to do by hand: derive the roll-up fields from the
four per-rule decisions, and check every completed row against
manual_review_schema.validate_row().

Why this exists
------------------
A reviewer only ever fills in e4_decision/e4_reason_code/e4_
supporting_text/e4_confidence (and the same for E5/E6/E8) - those are
the actual judgement calls. original_manual_decision, second_review_
required, and (on a first pass) final_reviewed_decision are NOT
judgement calls, they are pure functions of the four per-rule fields
(manual_review_schema.derive_overall_decision /
needs_second_review_flag) - computing them by hand risks exactly the
kind of transcription slip validate_row() exists to catch, so this
script computes them instead.

What this does and does not touch
-------------------------------------
For every row where all four *_decision fields are filled in:
  - if original_manual_decision is still blank, fills it in (this is
    the FIRST time the roll-up is computed for this row - see module
    docstring in manual_review_schema.py on why original_manual_
    decision is written once and never touched again after that)
  - if final_reviewed_decision is also still blank, defaults it to
    equal the freshly-computed original (nothing has been corrected
    yet - a real second-review correction is still something a human
    types in later, by changing final_reviewed_decision and filling
    correction_reason, never something this script infers)
  - always recomputes second_review_required (safe to refresh every
    run, since it is fully determined by the current four decisions,
    unlike original_manual_decision which must freeze at first review)
  - runs validate_row() and collects every problem found

Rows that are still blank (untouched) are left alone and counted
separately - they are not errors, just not started yet.

Usage:
    python3 -m src.news_collection.finalize_manual_review
    python3 -m src.news_collection.finalize_manual_review --file news_collection/manual_review_kappa_subset.csv
"""

import argparse
import csv
from pathlib import Path

from .manual_review_schema import (RULES, ValidationError,
                                   derive_overall_decision,
                                   needs_second_review_flag, validate_row)

DEFAULT_FILE = Path("news_collection/manual_review_sample.csv")


def row_is_untouched(row):
    return all(not row.get(f"{r.lower()}_decision") for r in RULES)


def finalize_row(row):
    """Fill in the derived fields in place. Returns nothing - mutates
    row, since the caller needs the same dict written back to the CSV."""
    e4, e5, e6, e8 = (row.get(f"{r.lower()}_decision") for r in RULES)
    if not row.get("original_manual_decision"):
        row["original_manual_decision"] = derive_overall_decision(
            e4, e5, e6, e8)
        if not row.get("final_reviewed_decision"):
            row["final_reviewed_decision"] = row["original_manual_decision"]
    row["second_review_required"] = str(
        needs_second_review_flag(e4, e5, e6, e8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE)
    args = ap.parse_args()

    rows = list(csv.DictReader(args.file.open()))
    fieldnames = list(rows[0].keys())

    untouched, finalized, invalid = 0, 0, []
    for row in rows:
        if row_is_untouched(row):
            untouched += 1
            continue
        missing = [r for r in RULES if not row.get(f"{r.lower()}_decision")]
        if missing:
            invalid.append((row["article_id"],
                           [f"{r}: no decision recorded yet" for r in missing]))
            continue
        finalize_row(row)
        try:
            validate_row(row, context=row["article_id"])
            finalized += 1
        except ValidationError as e:
            invalid.append((row["article_id"], str(e).split("\n  - ")[1:]))

    with args.file.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"{args.file}: {len(rows)} rows total")
    print(f"  not started: {untouched}")
    print(f"  complete and valid: {finalized}")
    print(f"  started but has problems: {len(invalid)}")
    if invalid:
        print("\nRows needing fixes:")
        for article_id, problems in invalid:
            print(f"  {article_id}:")
            for p in problems:
                print(f"    - {p}")


if __name__ == "__main__":
    main()
