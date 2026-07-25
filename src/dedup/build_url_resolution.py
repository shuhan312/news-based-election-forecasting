"""Phase 5 / Step 2 runner: canonical URL resolution over the frozen
corpus snapshot.

Inputs (read-only): the Phase 4 layer (original_url per article),
Step 1's mapping (body hashes - the content witness), and the raw
records (retrieved_at timestamps). No live requests are made.

Outputs (versioned _v1_provisional to match the input snapshot; no
article text, all tracked):

    news_collection/url_duplicate_mapping_v1_provisional.csv
    news_collection/url_groups_v1_provisional.jsonl
    news_collection/url_resolution_review_queue_v1_provisional.csv
    news_collection/url_resolution_summary_v1_provisional.md

Usage:
    python3 -m src.dedup.build_url_resolution
"""

import csv
import json
from collections import Counter
from pathlib import Path

from .url_canonical import RULE_VERSION, resolve_url_groups

LAYER = Path("news_collection/normalised_text_layer_v1_provisional.jsonl")
STEP1_MAP = Path(
    "news_collection/exact_duplicate_mapping_v1_provisional.csv")
RECORDS = Path("data/raw/news/records")

OUT_MAP = Path("news_collection/url_duplicate_mapping_v1_provisional.csv")
OUT_GROUPS = Path("news_collection/url_groups_v1_provisional.jsonl")
OUT_REVIEW = Path(
    "news_collection/url_resolution_review_queue_v1_provisional.csv")
OUT_MD = Path("news_collection/url_resolution_summary_v1_provisional.md")

FIELDS = ["article_id", "original_url", "canonical_url",
          "transformations", "wayback_capture_ts", "retrieved_at",
          "group_id", "group_size", "body_hash", "relationship",
          "flags", "rule_version"]

REVIEW_RELATIONSHIPS = {"same_url_content_changed",
                        "url_variant_probable_same_page",
                        "ambiguous_url_relationship"}


def main() -> None:
    body_hash = {r["article_id"]: r["body_hash"]
                 for r in csv.DictReader(STEP1_MAP.open())}

    records = []
    for line in LAYER.open():
        art = json.loads(line)
        aid = art["article_id"]
        rec_path = RECORDS / f"{aid}.json"
        retrieved = ""
        if rec_path.exists():
            retrieved = (json.loads(rec_path.read_text())
                         .get("retrieval") or {}).get("retrieved_at", "")
        records.append({"article_id": aid,
                        "original_url": art.get("original_url", ""),
                        "body_hash": body_hash.get(aid, ""),
                        "retrieved_at": retrieved})

    res = resolve_url_groups(records)

    rel_counts, flag_counts = Counter(), Counter()
    map_rows, review_rows = [], []
    for r in res["mapping"]:
        rel_counts[r["relationship"]] += 1
        for f in r["flags"]:
            flag_counts[f] += 1
        row = {"article_id": r["article_id"],
               "original_url": r["original_url"],
               "canonical_url": r["canonical"],
               "transformations": ";".join(r["transforms"]),
               "wayback_capture_ts": r["capture_ts"],
               "retrieved_at": r["retrieved_at"],
               "group_id": r["group_id"], "group_size": r["group_size"],
               "body_hash": (r.get("body_hash") or "")[:16],
               "relationship": r["relationship"],
               "flags": ";".join(r["flags"]),
               "rule_version": RULE_VERSION}
        map_rows.append(row)
        if r["relationship"] in REVIEW_RELATIONSHIPS:
            review_rows.append(row)

    assert len(map_rows) == len(records), "population mismatch"

    with OUT_MAP.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(map_rows)
    with OUT_GROUPS.open("w") as fh:
        for g in res["groups"]:
            fh.write(json.dumps(g, ensure_ascii=False) + "\n")
    with OUT_REVIEW.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(review_rows)

    multi = [g for g in res["groups"] if g["size"] > 1]
    OUT_MD.write_text(
        "# URL resolution - Step 2 summary (v1 provisional)\n\n"
        f"* rules: `{RULE_VERSION}`\n"
        f"* articles mapped: **{len(map_rows)}** (population asserted)\n"
        f"* URL groups: {len(res['groups'])} ({len(multi)} with more "
        "than one member)\n"
        f"* relationships: {dict(rel_counts)}\n"
        f"* flags: {dict(flag_counts)}\n"
        f"* review queue: {len(review_rows)} rows\n\n"
        "Original URLs are preserved verbatim; the canonical form is a "
        "comparison key only. URL equality never decides an article "
        "relationship by itself - content evidence comes from Step 1's "
        "hashes, and possible updated versions are handed to Step 3, "
        "not adjudicated here.\n")

    print(f"{len(map_rows)} articles mapped -> {OUT_MAP}")
    print("relationships:", dict(rel_counts))
    print(f"groups: {len(res['groups'])} ({len(multi)} multi-member)")
    print("flags:", dict(flag_counts))
    print(f"review queue: {len(review_rows)} -> {OUT_REVIEW}")


if __name__ == "__main__":
    main()
