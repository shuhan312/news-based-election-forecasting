"""Phase 4 / Step 5 runner: resolve field boundaries for every Step 4
article.

Inputs (read-only): Step 4's versioned JSONL, the Guardian API
sidecars (publisher metadata - the specification's "source metadata
first"), and the Step 4 review-resolution table: the nine
sentence_per_line articles that the human reviewer resolved as
structure_ok_keep are processed normally here, per that recorded
decision; the six no-content rows stay review_required.

Outputs (versioned, deterministic):

    news_collection/structured_articles_v1.jsonl   (full text ->
        gitignored with the rest of the corpus text)
    news_collection/text_boundary_log_v1.csv       (tracked, no text)
    news_collection/text_boundary_review_queue_v1.csv

Usage:
    python3 -m src.normalisation.build_structured_articles
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .boundary_resolve import (LLM_INPUT_COMPOSITION, RULE_VERSION,
                               resolve_fields)

IN_JSONL = Path("news_collection/structure_normalised_articles_v1.jsonl")
RESOLUTIONS = Path("news_collection/structure_review_resolutions_v1.csv")
API_RAW_DIR = Path("data/raw/news/api_raw")
OUT_JSONL = Path("news_collection/structured_articles_v1.jsonl")
OUT_LOG = Path("news_collection/text_boundary_log_v1.csv")
OUT_REVIEW = Path("news_collection/text_boundary_review_queue_v1.csv")

LOG_FIELDS = ["article_id", "status", "title_source", "author_source",
              "title_repeat_removed", "n_body_paragraphs", "n_captions",
              "n_supporting", "flags", "input_sha256", "output_sha256",
              "llm_input_composition", "rule_version"]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    resolved_ok = {r["article_id"]
                   for r in csv.DictReader(RESOLUTIONS.open())
                   if r["decision"] == "structure_ok_keep"}
    rows = [json.loads(line) for line in IN_JSONL.open()]
    rows.sort(key=lambda r: r["article_id"])

    out_rows, log_rows, review_rows = [], [], []
    statuses, flag_totals = Counter(), Counter()
    title_sources = Counter()
    repeats_removed = 0

    for r in rows:
        aid = r["article_id"]
        # Step 4 review rows: honour the human resolution table.
        if r["status"] == "review_required" and aid not in resolved_ok:
            statuses["review_required"] += 1
            row = {"article_id": aid, "status": "review_required",
                   "title_source": "", "author_source": "",
                   "title_repeat_removed": False,
                   "n_body_paragraphs": 0, "n_captions": 0,
                   "n_supporting": 0, "flags": "carried_from_step4",
                   "input_sha256": "", "output_sha256": "",
                   "llm_input_composition": LLM_INPUT_COMPOSITION,
                   "rule_version": RULE_VERSION}
            log_rows.append(row)
            review_rows.append(row)
            out_rows.append({"article_id": aid,
                             "status": "review_required",
                             "warning_flags": ["carried_from_step4"],
                             "rule_version": RULE_VERSION})
            continue

        api_path = API_RAW_DIR / f"{aid}.json"
        api_meta = (json.loads(api_path.read_text())
                    if api_path.exists() else None)
        res = resolve_fields(r, api_meta)

        status = "review_required" if res["review_required"] \
            else "structured"
        statuses[status] += 1
        for f in res["warning_flags"]:
            flag_totals[f] += 1
        title_sources[res["field_provenance"]["title"]] += 1
        if res["title_repeat_removed"]:
            repeats_removed += 1

        log_row = {
            "article_id": aid, "status": status,
            "title_source": res["field_provenance"]["title"],
            "author_source": res["field_provenance"]["author"],
            "title_repeat_removed": res["title_repeat_removed"],
            "n_body_paragraphs": len(res["body_paragraphs"]),
            "n_captions": len(res["caption_text"]),
            "n_supporting": len(res["supporting_text"]),
            "flags": ";".join(sorted(res["warning_flags"])),
            "input_sha256": sha256(r["body"]),
            "output_sha256": sha256(res["body_text"]),
            "llm_input_composition": LLM_INPUT_COMPOSITION,
            "rule_version": RULE_VERSION,
        }
        log_rows.append(log_row)
        if status == "review_required":
            review_rows.append(log_row)
        out_rows.append({"article_id": aid, "status": status, **res})

    with OUT_JSONL.open("w") as fh:
        for row in out_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    for path, rows_ in ((OUT_LOG, log_rows), (OUT_REVIEW, review_rows)):
        with path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
            w.writeheader()
            w.writerows(rows_)

    print(f"{len(log_rows)} articles -> {OUT_JSONL}")
    print("statuses:", dict(statuses))
    print("title sources:", dict(title_sources))
    print("title repeats removed:", repeats_removed)
    print("flags:", dict(flag_totals))
    print(f"review queue: {len(review_rows)} -> {OUT_REVIEW}")


if __name__ == "__main__":
    main()
