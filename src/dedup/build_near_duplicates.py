"""Phase 5 / Step 3 runner: near-duplicate detection over the frozen
corpus snapshot.

Inputs (read-only): the Phase 4 layer (titles/bodies), Step 1's
mapping (exact-duplicate pairs to exclude-but-reference), Step 2's
groups (multi-member URL groups as guaranteed candidates). Only
articles whose downstream status is usable text take part; snippets
and missing bodies cannot be meaningfully shingled.

Outputs (versioned _v1_provisional; pair evidence carries scores and
counts, never article text - all tracked):

    news_collection/near_duplicate_pairs_v1_provisional.csv
    news_collection/near_duplicate_clusters_v1_provisional.jsonl
    news_collection/near_duplicate_review_queue_v1_provisional.csv
    news_collection/near_duplicate_summary_v1_provisional.md

Usage:
    python3 -m src.dedup.build_near_duplicates
"""

import csv
import json
from collections import Counter
from pathlib import Path

from .near_duplicates import RULE_VERSION, detect_near_duplicates

LAYER = Path("news_collection/normalised_text_layer_v1_provisional.jsonl")
STEP1_MAP = Path(
    "news_collection/exact_duplicate_mapping_v1_provisional.csv")
STEP2_GROUPS = Path("news_collection/url_groups_v1_provisional.jsonl")

OUT_PAIRS = Path(
    "news_collection/near_duplicate_pairs_v1_provisional.csv")
OUT_CLUSTERS = Path(
    "news_collection/near_duplicate_clusters_v1_provisional.jsonl")
OUT_REVIEW = Path(
    "news_collection/near_duplicate_review_queue_v1_provisional.csv")
OUT_MD = Path("news_collection/near_duplicate_summary_v1_provisional.md")

FIELDS = ["article_id_a", "article_id_b", "source_a", "source_b",
          "jaccard", "containment", "title_sim", "seq_ratio",
          "length_ratio", "shared_shingles", "classification",
          "review_reason", "flags", "rule_version"]


def main() -> None:
    articles = []
    for line in LAYER.open():
        art = json.loads(line)
        if art.get("downstream_status") in ("ready_full_text",
                                            "ready_partial_text"):
            articles.append({"article_id": art["article_id"],
                             "title": art.get("title", ""),
                             "body_text": art.get("body_text", ""),
                             "source_name": art.get("source_name", "")})

    exact_pairs = set()
    by_cluster = {}
    for r in csv.DictReader(STEP1_MAP.open()):
        if r["cluster_id"]:
            by_cluster.setdefault(r["cluster_id"], []).append(
                r["article_id"])
    for ids in by_cluster.values():
        for i, x in enumerate(sorted(ids)):
            for y in sorted(ids)[i + 1:]:
                exact_pairs.add(frozenset((x, y)))

    url_pairs = set()
    for line in STEP2_GROUPS.open():
        g = json.loads(line)
        if g["size"] > 1:
            ms = sorted(g["member_ids"])
            for i, x in enumerate(ms):
                for y in ms[i + 1:]:
                    url_pairs.add(frozenset((x, y)))

    res = detect_near_duplicates(articles, exact_pairs, url_pairs)

    cls_counts, flag_counts = Counter(), Counter()
    rows, review_rows = [], []
    for p in res["pairs"]:
        cls_counts[p["classification"]] += 1
        for f in p["flags"]:
            flag_counts[f] += 1
        row = {**p, "flags": ";".join(p["flags"])}
        rows.append(row)
        if p["classification"] == "manual_review":
            review_rows.append(row)

    with OUT_PAIRS.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(rows)
    with OUT_CLUSTERS.open("w") as fh:
        for c in res["clusters"]:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    with OUT_REVIEW.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(review_rows)

    OUT_MD.write_text(
        "# Near-duplicate detection - Step 3 summary (v1 provisional)\n\n"
        f"* rules: `{RULE_VERSION}`\n"
        f"* articles participating: {len(articles)} (usable text only)\n"
        f"* candidate pairs scored: **{len(rows)}**\n"
        f"* classifications: {dict(cls_counts)}\n"
        f"* provisional clusters: {len(res['clusters'])}\n"
        f"* flags: {dict(flag_counts)}\n"
        f"* review queue: {len(review_rows)} rows\n\n"
        "Classification rests on shared word sequences only - shared "
        "topics, names, places and dates never constitute duplicate "
        "evidence. Cross-publisher high-overlap pairs carry the "
        "possible_syndication_candidate flag for Step 4; nothing here "
        "is a final verdict and no record was deleted or merged.\n")

    print(f"{len(rows)} candidate pairs -> {OUT_PAIRS}")
    print("classifications:", dict(cls_counts))
    print(f"clusters: {len(res['clusters'])}")
    print("flags:", dict(flag_counts))
    print(f"review queue: {len(review_rows)} -> {OUT_REVIEW}")


if __name__ == "__main__":
    main()
