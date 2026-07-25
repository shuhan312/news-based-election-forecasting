"""Phase 5 / Step 1 runner: exact-duplicate detection over the frozen
Phase 4 layer.

Input (read-only): normalised_text_layer_v1_provisional.jsonl.
Outputs versioned to match (_v1_provisional):

    news_collection/exact_duplicate_mapping_v1_provisional.csv
    news_collection/exact_duplicate_clusters_v1_provisional.jsonl
    news_collection/exact_duplicate_review_queue_v1_provisional.csv
    news_collection/exact_duplicate_summary_v1_provisional.md

None of these contain article text (hashes and ids only), so all are
tracked in Git.

Usage:
    python3 -m src.dedup.build_exact_duplicates
"""

import csv
import json
from collections import Counter
from pathlib import Path

from .exact_duplicates import RULE_VERSION, detect_exact_duplicates

IN_LAYER = Path("news_collection/normalised_text_layer_v1_provisional.jsonl")
OUT_MAP = Path("news_collection/exact_duplicate_mapping_v1_provisional.csv")
OUT_CLUSTERS = Path(
    "news_collection/exact_duplicate_clusters_v1_provisional.jsonl")
OUT_REVIEW = Path(
    "news_collection/exact_duplicate_review_queue_v1_provisional.csv")
OUT_MD = Path("news_collection/exact_duplicate_summary_v1_provisional.md")

FIELDS = ["article_id", "quality_status", "downstream_status",
          "title_hash", "body_hash", "composite_hash",
          "exact_duplicate_status", "cluster_id", "cluster_size",
          "evidence_basis", "flags", "rule_version"]


def main() -> None:
    articles = [json.loads(l) for l in IN_LAYER.open()]
    res = detect_exact_duplicates(articles)

    statuses, flag_totals = Counter(), Counter()
    map_rows, review_rows = [], []
    for r in res["mapping"]:
        statuses[r["exact_duplicate_status"]] += 1
        for f in r["flags"]:
            flag_totals[f] += 1
        row = {"article_id": r["article_id"],
               "quality_status": r["quality_status"],
               "downstream_status": r["downstream_status"],
               "title_hash": r["title_hash"][:16],
               "body_hash": r["body_hash"][:16],
               "composite_hash": r["composite_hash"][:16],
               "exact_duplicate_status": r["exact_duplicate_status"],
               "cluster_id": r["cluster_id"],
               "cluster_size": r["cluster_size"],
               "evidence_basis": ("identical non-empty body_hash"
                                  if r["cluster_id"] else ""),
               "flags": ";".join(r["flags"]),
               "rule_version": RULE_VERSION}
        map_rows.append(row)
        if r["flags"]:
            review_rows.append(row)

    assert len(map_rows) == len(articles), "population mismatch"

    with OUT_MAP.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(map_rows)
    with OUT_CLUSTERS.open("w") as fh:
        for c in res["clusters"]:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    with OUT_REVIEW.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(review_rows)

    dup_records = statuses.get("exact_duplicate", 0)
    OUT_MD.write_text(
        "# Exact duplicate detection - Step 1 summary (v1 provisional)\n\n"
        f"* rules: `{RULE_VERSION}` | input: `{IN_LAYER.name}`\n"
        f"* articles mapped: **{len(map_rows)}** (equals the Phase 4 "
        "population; asserted)\n"
        f"* statuses: {dict(statuses)}\n"
        f"* clusters: **{len(res['clusters'])}** covering "
        f"{dup_records} records\n"
        f"* flags: {dict(flag_totals)}\n\n"
        "Relationships only: nothing was deleted, merged or chosen as "
        "canonical. Cluster ids are body-hash-derived, so future "
        "releases cannot rename untouched clusters.\n")

    print(f"{len(map_rows)} articles mapped -> {OUT_MAP}")
    print("statuses:", dict(statuses))
    print(f"clusters: {len(res['clusters'])} covering {dup_records} records")
    print("flags:", dict(flag_totals))
    print(f"review queue: {len(review_rows)} -> {OUT_REVIEW}")


if __name__ == "__main__":
    main()
