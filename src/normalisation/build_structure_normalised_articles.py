"""Phase 4 / Step 4 runner: structure-normalise every Step 3 article.

Input is SOLELY Step 3's versioned output
(character_normalised_articles_v1.jsonl); Steps 1-3 outputs and raw
records are read, never written. Step 3 review rows are carried
forward untouched - exactly one status per article, nothing silently
dropped.

Outputs (versioned, deterministic):

    news_collection/structure_normalised_articles_v1.jsonl (full text
        -> gitignored with the rest of the corpus text)
    news_collection/structure_normalisation_log_v1.csv     (tracked)
    news_collection/structure_normalisation_review_queue_v1.csv

Usage:
    python3 -m src.normalisation.build_structure_normalised_articles
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .structure_normalise import RULE_VERSION, normalise_structure

IN_JSONL = Path("news_collection/character_normalised_articles_v1.jsonl")
OUT_JSONL = Path("news_collection/structure_normalised_articles_v1.jsonl")
OUT_LOG = Path("news_collection/structure_normalisation_log_v1.csv")
OUT_REVIEW = Path(
    "news_collection/structure_normalisation_review_queue_v1.csv")

LOG_FIELDS = ["article_id", "status", "input_sha256", "output_sha256",
              "input_lines", "output_lines", "input_paragraphs",
              "output_paragraphs", "transformations", "flags",
              "rule_version"]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    rows = [json.loads(line) for line in IN_JSONL.open()]
    rows.sort(key=lambda r: r["article_id"])   # stable ordering

    out_rows, log_rows, review_rows = [], [], []
    statuses, flag_totals, transform_totals = Counter(), Counter(), Counter()

    for r in rows:
        aid = r["article_id"]
        if r["status"] == "review_required":
            # Carried forward from Step 3 - no text to structure.
            statuses["review_required"] += 1
            row = {"article_id": aid, "status": "review_required",
                   "input_sha256": "", "output_sha256": "",
                   "input_lines": 0, "output_lines": 0,
                   "input_paragraphs": 0, "output_paragraphs": 0,
                   "transformations": "", "flags": "carried_from_step3",
                   "rule_version": RULE_VERSION}
            log_rows.append(row)
            review_rows.append(row)
            out_rows.append({"article_id": aid,
                             "status": "review_required",
                             "title": r.get("title", ""), "body": "",
                             "paragraphs": [],
                             "flags": ["carried_from_step3"],
                             "rule_version": RULE_VERSION})
            continue

        res = normalise_structure(r["paragraphs"])
        # The title is a single field: same whitespace rules apply via
        # a one-paragraph pass; its flags are irrelevant (one line by
        # definition) so only the text is taken.
        title = normalise_structure([r.get("title", "")])["body"]

        status = "review_required" if res["review_required"] \
            else "normalised"
        statuses[status] += 1
        transform_totals.update(res["transformations"])
        for f in res["flags"]:
            flag_totals[f] += 1

        log_row = {
            "article_id": aid, "status": status,
            "input_sha256": sha256(r["body"]),
            "output_sha256": sha256(res["body"]),
            "input_lines": r["body"].count("\n") + 1,
            "output_lines": res["body"].count("\n") + 1,
            "input_paragraphs": res["input_paragraphs"],
            "output_paragraphs": res["output_paragraphs"],
            "transformations": ";".join(
                f"{k}:{v}" for k, v in sorted(
                    res["transformations"].items())),
            "flags": ";".join(sorted(res["flags"])),
            "rule_version": RULE_VERSION,
        }
        log_rows.append(log_row)
        if status == "review_required":
            review_rows.append(log_row)
        out_rows.append({"article_id": aid, "status": status,
                         "title": title, "body": res["body"],
                         "paragraphs": res["paragraphs"],
                         "flags": sorted(res["flags"]),
                         "output_sha256": sha256(res["body"]),
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
