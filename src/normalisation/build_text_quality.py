"""Phase 4 / Step 6 runner: assess text quality for every Step 5
article.

Reads (never writes): Step 5's versioned JSONL, plus the upstream
evidence this layer folds in - the Step 1 manifest (completeness),
the Step 3 and Step 4 logs (encoding/structure warnings), and the two
human resolution tables (structure keeps, media-only). One status per
article; population count must equal Step 5's, asserted at the end.

Outputs (versioned, deterministic, no article text):

    news_collection/text_quality_results_v1.csv
    news_collection/text_quality_review_queue_v1.csv
    news_collection/text_quality_summary_v1.md

Usage:
    python3 -m src.normalisation.build_text_quality
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .text_quality import RULE_VERSION, assess_quality

IN_JSONL = Path("news_collection/structured_articles_v1.jsonl")
STEP1 = Path("news_collection/normalisation_input_manifest_v1.csv")
STEP3_LOG = Path("news_collection/character_normalisation_log_v1.csv")
STEP4_LOG = Path("news_collection/structure_normalisation_log_v1.csv")
MEDIA_RES = Path("news_collection/missing_text_resolutions_v1.csv")
STRUCT_RES = Path("news_collection/structure_review_resolutions_v1.csv")

OUT_CSV = Path("news_collection/text_quality_results_v1.csv")
OUT_REVIEW = Path("news_collection/text_quality_review_queue_v1.csv")
OUT_MD = Path("news_collection/text_quality_summary_v1.md")

FIELDS = ["article_id", "quality_status", "status_reason",
          "body_words", "body_chars", "title_words", "summary_words",
          "paragraphs", "boilerplate_density", "duplicate_paragraphs",
          "step1_status", "warning_flags", "review_required",
          "input_sha256", "output_sha256", "rule_version"]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_upstream() -> dict[str, dict]:
    """Fold every earlier layer's evidence into one dict per id."""
    up: dict[str, dict] = {}
    for r in csv.DictReader(STEP1.open()):
        up.setdefault(r["article_id"], {})["step1_status"] = \
            r["text_completeness_status"]
    for r in csv.DictReader(STEP3_LOG.open()):
        up.setdefault(r["article_id"], {})["step3_flags"] = \
            [f for f in r["flags"].split(";") if f
             and f != "carried_from_step2"]
    for r in csv.DictReader(STEP4_LOG.open()):
        up.setdefault(r["article_id"], {})["step4_flags"] = \
            [f for f in r["flags"].split(";") if f]
    for r in csv.DictReader(MEDIA_RES.open()):
        up.setdefault(r["article_id"], {})["media_resolution"] = True
    for r in csv.DictReader(STRUCT_RES.open()):
        up.setdefault(r["article_id"], {})["structure_resolution"] = True
    return up


def main() -> None:
    upstream = load_upstream()
    rows = [json.loads(line) for line in IN_JSONL.open()]
    rows.sort(key=lambda r: r["article_id"])

    out_rows, review_rows = [], []
    statuses, flag_totals = Counter(), Counter()

    for r in rows:
        aid = r["article_id"]
        res = assess_quality(r, upstream.get(aid, {}))
        statuses[res["quality_status"]] += 1
        for f in res["warning_flags"]:
            flag_totals[f] += 1
        s = res["signals"]
        row = {
            "article_id": aid,
            "quality_status": res["quality_status"],
            "status_reason": res["status_reason"],
            "body_words": s.get("body_words", 0),
            "body_chars": s.get("body_chars", 0),
            "title_words": s.get("title_words", 0),
            "summary_words": s.get("summary_words", 0),
            "paragraphs": s.get("paragraphs", 0),
            "boilerplate_density": s.get("boilerplate_density", ""),
            "duplicate_paragraphs": s.get("duplicate_paragraphs", ""),
            "step1_status": s.get("step1_status", ""),
            "warning_flags": ";".join(res["warning_flags"]),
            "review_required": res["review_required"],
            "input_sha256": sha256(r.get("body_text") or ""),
            "output_sha256": sha256(r.get("body_text") or ""),
            "rule_version": res["rule_version"],
        }
        out_rows.append(row)
        if res["review_required"]:
            review_rows.append(row)

    # Coverage invariant: exactly one status per Step 5 article.
    assert len(out_rows) == len(rows), "population mismatch"

    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out_rows)
    with OUT_REVIEW.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(review_rows)

    OUT_MD.write_text(
        "# Text quality - Step 6 summary (v1)\n\n"
        f"* rules: `{RULE_VERSION}`\n"
        f"* articles assessed: **{len(out_rows)}** (equals the Step 5 "
        "population; input body hash recorded per row - this step "
        "never edits text, so output hash == input hash)\n"
        f"* statuses: {dict(statuses)}\n"
        f"* warning flags: {dict(flag_totals)}\n"
        f"* review queue: {len(review_rows)} rows\n\n"
        "Status rules and thresholds are documented in "
        "`src/normalisation/text_quality.py`.\n")

    print(f"{len(out_rows)} articles -> {OUT_CSV}")
    print("statuses:", dict(statuses))
    print("flags:", dict(flag_totals))
    print(f"review queue: {len(review_rows)} -> {OUT_REVIEW}")


if __name__ == "__main__":
    main()
