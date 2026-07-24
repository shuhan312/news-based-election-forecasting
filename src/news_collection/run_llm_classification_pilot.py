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
import shutil
from datetime import datetime
from pathlib import Path

from .llm_classifier import classify_article
from .manual_review_schema import RULES

SAMPLE = Path("news_collection/manual_review_sample.csv")
OUT = Path("news_collection/manual_review_llm_pilot.csv")

# Verbatim model output for every response that failed to parse, one
# file per article. Without this, a parse_error row records only the
# json.loads() message - not WHAT the model actually sent - so failures
# can't be diagnosed (the first pilot run's 39 fence-wrapped responses
# had to be inferred from the error text alone) and the audit trail has
# a hole exactly where the pipeline misbehaved.
RAW_FAILURE_DIR = Path("news_collection/llm_pilot_unparsed_responses")

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


def load_previous_ok_rows():
    """Rows from an earlier run of this script that already carry a
    real classification (status=ok), keyed by article_id.

    Re-run semantics, and why they matter: the model is stochastic, so
    re-requesting an article that ALREADY has a recorded classification
    would re-roll the dice on it - and even an accidental "keep the
    re-run because its kappa looks better" is a form of cherry-picking
    the validation must not permit. So successful classifications are
    carried forward verbatim and never re-requested; only articles with
    NO usable classification on record (parse_error / api_error /
    not_configured) are attempted again. For those, a fresh attempt
    replaces a gap, not an answer - each article ends up with exactly
    one recorded classification, from whichever run first produced one.
    """
    if not OUT.exists():
        return {}
    with OUT.open() as fh:
        return {r["article_id"]: r for r in csv.DictReader(fh)
               if r.get("status") == "ok"}


def backup_previous_output():
    """Copy the existing output aside (timestamped) before overwriting,
    so every run's raw result stays inspectable - the audit trail for
    "what did the first run actually say" must survive the re-run."""
    if OUT.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = OUT.with_name(f"{OUT.stem}.pre-rerun-{stamp}{OUT.suffix}")
        shutil.copy2(OUT, backup)
        print(f"previous output backed up -> {backup}")


def main():
    rows = [r for r in csv.DictReader(SAMPLE.open())
           if r["review_round"] == "initial"]

    previous_ok = load_previous_ok_rows()
    backup_previous_output()

    out_rows = []
    status_counts = {}
    kept, reran = 0, 0
    for row in rows:
        # Carry forward an article that already has a real
        # classification - see load_previous_ok_rows() for why this is
        # never re-requested.
        if row["article_id"] in previous_ok:
            out_rows.append(previous_ok[row["article_id"]])
            status_counts["ok"] = status_counts.get("ok", 0) + 1
            kept += 1
            continue

        article = article_from_sample_row(row)
        result = classify_article(article)
        status = result.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        reran += 1

        # Keep the un-parseable response itself, verbatim, for
        # diagnosis - see RAW_FAILURE_DIR's comment.
        if status == "parse_error" and result.get("raw_text"):
            RAW_FAILURE_DIR.mkdir(parents=True, exist_ok=True)
            (RAW_FAILURE_DIR / f"{row['article_id']}.txt").write_text(
                result["raw_text"])

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

    if previous_ok:
        print(f"{kept} article(s) carried forward from the previous run, "
             f"{reran} attempted this run")

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
