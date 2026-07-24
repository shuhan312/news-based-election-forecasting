"""Run the LLM classifier (llm_classifier.py) against the same 168
articles a human is reviewing in manual_review_sample.csv, so the two
can later be compared.

What this writes, and what it deliberately does NOT do
----------------------------------------------------------
Output goes to news_collection/manual_review_llm_pilot.csv only - a
new file, never manual_review_sample.csv itself (the human's answers
and the LLM's answers must never share a column, or a later "compare
the two" step would be comparing a value against itself). This script
never calls manual_review_schema.is_eligible_for_downstream() and
nothing it produces is read by any other pipeline stage - an LLM
classification only counts as usable evidence once compare_llm_to_
human_agreement.py shows it agrees with the human pilot review at or
above the same 0.60 kappa bar used for the human blind recheck (see
llm_classifier.py's docstring). Below that bar, the affected rule
stays fully manual regardless of what this script produces.

Usage:
    python3 -m src.news_collection.run_llm_classification_pilot
"""

import csv
from pathlib import Path

from .llm_classifier import classify_article
from .manual_review_schema import RULES

SAMPLE = Path("news_collection/manual_review_sample.csv")
OUT = Path("news_collection/manual_review_llm_pilot.csv")

FIELDNAMES = (
    ["article_id", "status", "note"] +
    [f"{r.lower()}_decision" for r in RULES] +
    [f"{r.lower()}_reason_code" for r in RULES] +
    [f"{r.lower()}_supporting_text" for r in RULES] +
    [f"{r.lower()}_confidence" for r in RULES]
)


def article_from_sample_row(row):
    day_index = row.get("day_index_from_polling_day")
    return {
        "headline": row["headline"],
        "text": row["article_text_excerpt"],
        "source_id": row["source_id"], "election_id": row["election_id"],
        "arm": row["arm"],
        "day_index_from_polling_day": int(day_index) if day_index else None,
        "needs_reform_disambiguation": row["needs_reform_disambiguation"],
    }


def main():
    rows = [r for r in csv.DictReader(SAMPLE.open())
           if r["review_round"] == "initial"]

    out_rows = []
    status_counts = {}
    for row in rows:
        article = article_from_sample_row(row)
        result = classify_article(article)
        status = result.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        out_row = {"article_id": row["article_id"], "status": status,
                  "note": result.get("note", "")}
        for rule in RULES:
            prefix = rule.lower()
            out_row[f"{prefix}_decision"] = result.get(f"{prefix}_decision", "")
            out_row[f"{prefix}_reason_code"] = result.get(
                f"{prefix}_reason_code", "")
            out_row[f"{prefix}_supporting_text"] = result.get(
                f"{prefix}_supporting_text", "")
            out_row[f"{prefix}_confidence"] = result.get(
                f"{prefix}_confidence", "")
        out_rows.append(out_row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(out_rows)

    print(f"{len(out_rows)} articles processed -> {OUT}")
    print("by status:", status_counts)
    if status_counts.get("not_configured"):
        print(f"\n{status_counts['not_configured']} article(s) produced NO "
             "classification - ANTHROPIC_API_KEY is not set. Nothing "
             "here should be treated as a real result (see module "
             "docstring).")
    if status_counts.get("ok"):
        print(f"\n{status_counts['ok']} article(s) received a real "
             "classification. Before using ANY of this, the per-rule "
             "kappa check against the human pilot must clear 0.60 - "
             "see compare_llm_to_human_agreement.py and this module's "
             "docstring.")


if __name__ == "__main__":
    main()
