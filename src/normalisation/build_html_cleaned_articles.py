"""Phase 4 / Step 2 runner: apply html_clean to every eligible
article and version the outputs.

Scope and provenance rules:

* The article list comes ONLY from Step 1's frozen manifest
  (normalisation_input_manifest_v1.csv). No eligibility logic lives here.
* Raw evidence is read, never written: data/raw/news/html/{id}.html
  and the API text files stay byte-identical (asserted by the tests).
* Articles WITHOUT an HTML sidecar (the Guardian API route delivers
  clean bodyText, no page) pass through with method=api_text and the
  Step 1 text; they still receive exactly one status each, so the
  output accounts for every eligible article.
* Nothing is dropped silently: empty/suspicious extractions land in
  the review queue with their warnings, and the JSONL row is still
  written with status=review_required.

Outputs (versioned, deterministic - no timestamps inside):

    news_collection/html_cleaned_articles_v1.jsonl
    news_collection/html_cleaning_log_v1.csv
    news_collection/html_cleaning_review_queue_v1.csv

Usage:
    python3 -m src.news_collection.build_html_cleaned_articles
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .html_clean import RULE_VERSION, clean_html

INPUTS = Path("news_collection/normalisation_input_manifest_v1.csv")
HTML_DIR = Path("data/raw/news/html")
OUT_JSONL = Path("news_collection/html_cleaned_articles_v1.jsonl")
OUT_LOG = Path("news_collection/html_cleaning_log_v1.csv")
OUT_REVIEW = Path("news_collection/html_cleaning_review_queue_v1.csv")

LOG_FIELDS = ["article_id", "source_id", "method", "input_path",
              "input_sha256", "selector_used", "title", "paragraph_count",
              "input_chars", "output_chars", "removed_ratio",
              "warnings", "status", "rule_version"]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    rows = sorted(csv.DictReader(INPUTS.open()),
                  key=lambda r: r["article_id"])
    jsonl_rows, log_rows, review_rows = [], [], []
    statuses = Counter()
    warn_counter = Counter()

    for r in rows:
        aid = r["article_id"]
        html_path = HTML_DIR / f"{aid}.html"
        source_id = aid.split("-")[1] if aid.count("-") >= 2 else ""

        if html_path.exists():
            html = html_path.read_text(errors="replace")
            res = clean_html(html, source_id=source_id)
            method = "html_parse"
            input_path, input_hash = str(html_path), sha256(html)
        elif r["text_completeness_status"] in ("full_text", "partial_text"):
            # API-delivered body (no web page to clean). Passed through
            # unchanged: entity decoding etc. already happened at the
            # publisher API. Verified against Step 1's frozen hash so a
            # drifted file is refused, not silently used.
            text = Path(r["selected_text_source_path_or_reference"]).read_text(errors="replace")
            if sha256(text) != r["selected_text_source_hash"]:
                res = {"title": "", "body": "", "paragraphs": [],
                       "selector_used": "", "status": "review_required",
                       "warnings": ["input_drifted"], "flagged_kept": [],
                       "input_chars": len(text), "output_chars": 0,
                       "removed_ratio": 1.0, "rule_version": RULE_VERSION}
            else:
                paras = [p for p in text.splitlines() if p.strip()]
                res = {"title": "", "body": text, "paragraphs": paras,
                       "selector_used": "api_text", "status": "cleaned",
                       "warnings": [], "flagged_kept": [],
                       "input_chars": len(text), "output_chars": len(text),
                       "removed_ratio": 0.0, "rule_version": RULE_VERSION}
            method = "api_text"
            input_path, input_hash = (r["selected_text_source_path_or_reference"],
                                      r["selected_text_source_hash"])
        else:
            # Eligible but no stored content at all (Step 1's
            # missing_text rows): an explicit review row, never a
            # silent drop.
            res = {"title": "", "body": "", "paragraphs": [],
                   "selector_used": "", "status": "review_required",
                   "warnings": ["no_stored_content"], "flagged_kept": [],
                   "input_chars": 0, "output_chars": 0,
                   "removed_ratio": 1.0, "rule_version": RULE_VERSION}
            method, input_path, input_hash = "none", "", ""

        statuses[res["status"]] += 1
        for w in res["warnings"]:
            warn_counter[w] += 1

        jsonl_rows.append({
            "article_id": aid, "source_id": source_id, "method": method,
            "input_path": input_path, "input_sha256": input_hash,
            "title": res["title"], "body": res["body"],
            "paragraphs": res["paragraphs"],
            "selector_used": res["selector_used"],
            "flagged_kept": res["flagged_kept"],
            "warnings": res["warnings"], "status": res["status"],
            "clean_sha256": sha256(res["body"]) if res["body"] else "",
            "rule_version": res["rule_version"],
        })
        log_rows.append({
            "article_id": aid, "source_id": source_id, "method": method,
            "input_path": input_path, "input_sha256": input_hash,
            "selector_used": res["selector_used"], "title": res["title"],
            "paragraph_count": len(res["paragraphs"]),
            "input_chars": res["input_chars"],
            "output_chars": res["output_chars"],
            "removed_ratio": res["removed_ratio"],
            "warnings": ";".join(res["warnings"]),
            "status": res["status"], "rule_version": res["rule_version"],
        })
        if res["status"] == "review_required":
            review_rows.append(log_rows[-1])

    with OUT_JSONL.open("w") as fh:
        for row in jsonl_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    for path, rows_ in ((OUT_LOG, log_rows), (OUT_REVIEW, review_rows)):
        with path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
            w.writeheader()
            w.writerows(rows_)

    print(f"{len(log_rows)} eligible articles -> {OUT_JSONL}")
    print("statuses:", dict(statuses))
    print("warnings:", dict(warn_counter))
    print(f"review queue: {len(review_rows)} rows -> {OUT_REVIEW}")


if __name__ == "__main__":
    main()
