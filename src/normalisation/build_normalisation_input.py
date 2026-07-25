"""Phase 4 / Step 1 runner: lock the eligible population, select each
article's text source, and freeze the versioned manifest Step 2
consumes.

Population comes ONLY from the frozen eligibility outputs (the corpus
decisions table plus the pilot and validation human sheets); this
module contains no eligibility logic and never re-runs E1-E10. The
eligibility and date-resolution layers are identified by content hash
(sha256 of the files as read), so the manifest states verifiably
WHICH version of each upstream layer it was locked against.

Outputs (all versioned _v1; deterministic - no timestamps inside):

    news_collection/normalisation_input_manifest_v1.csv    one row per
                                                           eligible article
    news_collection/normalisation_input_records_v1.jsonl   same rows plus
                                                           alternatives detail
    news_collection/normalisation_input_review_queue_v1.csv
    news_collection/normalisation_input_summary_v1.md      human-readable
    news_collection/normalisation_input_manifest_v1.json   machine-readable
                                                           summary + versions

None of these contain article text - references and hashes only - so
all five are safe to track in Git under the corpus-text/copyright
split.

Usage:
    python3 -m src.news_collection.build_normalisation_input
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .normalisation_input import (INPUT_SELECTION_VERSION, select_source,
                                  sha256)

DECISIONS = Path("news_collection/corpus_eligibility_decisions.csv")
PILOT = Path("news_collection/manual_review_sample.csv")
VALIDATION = Path("news_collection/llm_validation_sample.csv")
DATES = Path("news_collection/effective_dates.csv")
RECORDS = Path("data/raw/news/records")
HTML_DIR = Path("data/raw/news/html")
API_RAW_DIR = Path("data/raw/news/api_raw")

OUT_CSV = Path("news_collection/normalisation_input_manifest_v1.csv")
OUT_JSONL = Path("news_collection/normalisation_input_records_v1.jsonl")
OUT_REVIEW = Path("news_collection/normalisation_input_review_queue_v1.csv")
OUT_MD = Path("news_collection/normalisation_input_summary_v1.md")
OUT_JSON = Path("news_collection/normalisation_input_manifest_v1.json")

CSV_FIELDS = ["article_id", "eligibility_version",
              "date_resolution_version", "source_name", "original_url",
              "selected_text_source_type",
              "selected_text_source_path_or_reference",
              "selected_text_source_hash", "text_completeness_status",
              "selection_priority_rank", "selection_reason",
              "alternative_source_count", "alternative_source_references",
              "validation_flags", "review_required",
              "input_selection_version"]


def file_hash(path: Path) -> str:
    """Content hash used as the upstream layer's version identifier -
    two manifests are comparable only if they cite the same hashes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_eligible() -> dict[str, str]:
    """Final eligible ids -> which frozen layer decided them. Human
    sheets take precedence over the corpus table (their decisions are
    the more directly audited record)."""
    eligible = {}
    for r in csv.DictReader(DECISIONS.open()):
        if r["overall_decision"] == "include":
            eligible[r["article_id"]] = "corpus_decisions"
    for path, label in ((PILOT, "pilot_manual"),
                        (VALIDATION, "validation_manual")):
        for r in csv.DictReader(path.open()):
            if r.get("review_round") not in ("initial", "llm_validation"):
                continue
            final = (r.get("final_reviewed_decision")
                     or r.get("original_manual_decision"))
            if final == "include":
                eligible[r["article_id"]] = label
    return eligible


def main() -> None:
    eligibility_version = "elig-" + file_hash(DECISIONS)
    date_resolution_version = "dates-" + file_hash(DATES)
    eligible = load_eligible()

    rows, review_rows = [], []
    by_status, by_type, flag_counter = Counter(), Counter(), Counter()

    for aid in sorted(eligible):          # stable output ordering
        rec_path = RECORDS / f"{aid}.json"
        record = (json.loads(rec_path.read_text())
                  if rec_path.exists() else {"article_id": aid})
        record.setdefault("article_id", aid)
        res = select_source(record, html_dir=HTML_DIR,
                            api_raw_dir=API_RAW_DIR)
        res["eligibility_version"] = eligibility_version
        res["date_resolution_version"] = date_resolution_version
        if not rec_path.exists():
            # An eligible id with no raw record would mean upstream
            # corruption: surfaced loudly as review_required.
            res["validation_flags"].append("raw_record_missing")
            res["text_completeness_status"] = "review_required"
            res["review_required"] = True

        by_status[res["text_completeness_status"]] += 1
        by_type[res["selected_text_source_type"]] += 1
        for f in res["validation_flags"]:
            flag_counter[f] += 1
        rows.append(res)
        if res["review_required"]:
            review_rows.append(res)

    def csv_row(r):
        out = dict(r)
        out["alternative_source_references"] = \
            ";".join(r["alternative_source_references"])
        out["validation_flags"] = ";".join(r["validation_flags"])
        return {k: out[k] for k in CSV_FIELDS}

    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(csv_row(r) for r in rows)
    with OUT_JSONL.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with OUT_REVIEW.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(csv_row(r) for r in review_rows)

    summary = {
        "input_selection_version": INPUT_SELECTION_VERSION,
        "eligibility_version": eligibility_version,
        "date_resolution_version": date_resolution_version,
        "eligible_articles": len(rows),
        "by_completeness_status": dict(by_status),
        "by_selected_source_type": dict(by_type),
        "validation_flags": dict(flag_counter),
        "review_required": len(review_rows),
        "manifest_sha256": sha256(OUT_CSV.read_text()),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2) + "\n")
    OUT_MD.write_text(
        "# Normalisation input - Step 1 summary (v1)\n\n"
        f"* selection rules: `{INPUT_SELECTION_VERSION}`\n"
        f"* eligibility layer: `{eligibility_version}`  |  "
        f"date layer: `{date_resolution_version}`\n"
        f"* eligible articles: **{len(rows)}** (one row each)\n"
        f"* completeness: {dict(by_status)}\n"
        f"* selected source types: {dict(by_type)}\n"
        f"* validation flags: {dict(flag_counter)}\n"
        f"* review queue: {len(review_rows)} rows\n\n"
        "Source-priority policy and validation rules are documented in "
        "`src.normalisation_input.py`. No article text "
        "is stored in these outputs - references and hashes only.\n")

    print(f"{len(rows)} eligible articles -> {OUT_CSV}")
    print("by status:", dict(by_status))
    print("by source type:", dict(by_type))
    print("flags:", dict(flag_counter))
    print(f"review queue: {len(review_rows)} -> {OUT_REVIEW}")


if __name__ == "__main__":
    main()
