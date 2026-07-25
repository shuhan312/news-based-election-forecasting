"""Phase 4 / Step 3 runner: character-normalise every Step 2 article.

Input is SOLELY Step 2's versioned output
(html_cleaned_articles_v1.jsonl); raw records and Step 2 files are
read, never written. Paragraphs are normalised individually and the
body is rebuilt as their join, so paragraph boundaries survive
byte-identically and the whole pipeline stays idempotent.

Statuses (exactly one per Step 2 article):

    normalised          transformed (possibly zero transformations)
    review_required     carried forward from Step 2 (no text to
                        normalise) OR new encoding damage found here
                        (heavy U+FFFD presence)

Outputs (versioned, deterministic):

    news_collection/character_normalised_articles_v1.jsonl  (full text
        -> gitignored, like every corpus-text artefact)
    news_collection/character_normalisation_log_v1.csv      (no text,
        tracked)
    news_collection/character_normalisation_review_queue_v1.csv

Usage:
    python3 -m src.news_collection.build_char_normalised_articles
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .char_normalise import RULE_VERSION, normalise_text

IN_JSONL = Path("news_collection/html_cleaned_articles_v1.jsonl")
OUT_JSONL = Path("news_collection/character_normalised_articles_v1.jsonl")
OUT_LOG = Path("news_collection/character_normalisation_log_v1.csv")
OUT_REVIEW = Path(
    "news_collection/character_normalisation_review_queue_v1.csv")

LOG_FIELDS = ["article_id", "status", "input_sha256", "output_sha256",
              "unicode_form", "transformations", "chars_affected",
              "flags", "paragraph_count", "rule_version"]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    rows = [json.loads(line) for line in IN_JSONL.open()]
    rows.sort(key=lambda r: r["article_id"])   # stable ordering

    out_rows, log_rows, review_rows = [], [], []
    statuses, transform_totals, flag_totals = Counter(), Counter(), Counter()

    for r in rows:
        aid = r["article_id"]
        if r["status"] == "review_required" or not r.get("body"):
            # Step 2 already parked this article; carry the status
            # forward untouched - Step 3 has nothing to normalise and
            # must not invent an output for it.
            statuses["review_required"] += 1
            row = {"article_id": aid, "status": "review_required",
                   "input_sha256": "", "output_sha256": "",
                   "unicode_form": "NFC", "transformations": "",
                   "chars_affected": 0,
                   "flags": "carried_from_step2",
                   "paragraph_count": 0, "rule_version": RULE_VERSION}
            log_rows.append(row)
            review_rows.append(row)
            out_rows.append({"article_id": aid,
                             "status": "review_required",
                             "title": r.get("title", ""), "body": "",
                             "paragraphs": [],
                             "flags": ["carried_from_step2"],
                             "rule_version": RULE_VERSION})
            continue

        # Title and each paragraph normalised independently; the body
        # is REBUILT from the normalised paragraphs so body and
        # paragraphs can never drift apart.
        title_res = normalise_text(r.get("title", ""))
        para_results = [normalise_text(p) for p in r["paragraphs"]]
        paragraphs = [pr["text"] for pr in para_results]
        body = "\n\n".join(paragraphs)

        counts: Counter = Counter(title_res["transformations"])
        flags = set(title_res["flags"])
        for pr in para_results:
            counts.update(pr["transformations"])
            flags.update(pr["flags"])
        review = any(pr["review_required"] for pr in para_results)

        status = "review_required" if review else "normalised"
        statuses[status] += 1
        transform_totals.update(counts)
        for f in flags:
            flag_totals[f] += 1

        chars_affected = sum(counts.values())
        log_row = {
            "article_id": aid, "status": status,
            "input_sha256": sha256(r["body"]),
            "output_sha256": sha256(body),
            "unicode_form": "NFC",
            "transformations": ";".join(
                f"{k}:{v}" for k, v in sorted(counts.items())),
            "chars_affected": chars_affected,
            "flags": ";".join(sorted(flags)),
            "paragraph_count": len(paragraphs),
            "rule_version": RULE_VERSION,
        }
        log_rows.append(log_row)
        if status == "review_required":
            review_rows.append(log_row)
        out_rows.append({"article_id": aid, "status": status,
                         "title": title_res["text"], "body": body,
                         "paragraphs": paragraphs,
                         "flags": sorted(flags),
                         "output_sha256": sha256(body),
                         "rule_version": RULE_VERSION})

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
    print("transformations:", dict(transform_totals))
    print("flags:", dict(flag_totals))
    print(f"review queue: {len(review_rows)} -> {OUT_REVIEW}")


if __name__ == "__main__":
    main()
