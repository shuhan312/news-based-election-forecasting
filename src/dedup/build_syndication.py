"""Phase 5 / Step 4 runner: syndication identification over the
frozen corpus snapshot.

Inputs (read-only): Step 3's pair table (cross-publisher rows of any
scored class - the same-publisher pairs are Step 5's inbox and are
skipped here by design), the Phase 4 layer (bodies, paragraphs,
authors), Step 2's mapping (capture timestamps) and the upstream
effective dates (publication dates).

Outputs (versioned _v1_provisional; evidence carries scores, marker
strings and one sample paragraph - no full text - all tracked):

    news_collection/syndication_relationships_v1_provisional.csv
    news_collection/syndication_families_v1_provisional.jsonl
    news_collection/syndication_review_queue_v1_provisional.csv
    news_collection/syndication_summary_v1_provisional.md

Usage:
    python3 -m src.dedup.build_syndication
"""

import csv
import json
from collections import Counter
from pathlib import Path

from .syndication import RULE_VERSION, build_families, classify_pair

LAYER = Path("news_collection/normalised_text_layer_v1_provisional.jsonl")
PAIRS = Path("news_collection/near_duplicate_pairs_v1_provisional.csv")
URL_MAP = Path("news_collection/url_duplicate_mapping_v1_provisional.csv")
DATES = Path("news_collection/effective_dates.csv")

OUT_REL = Path(
    "news_collection/syndication_relationships_v1_provisional.csv")
OUT_FAM = Path(
    "news_collection/syndication_families_v1_provisional.jsonl")
OUT_REVIEW = Path(
    "news_collection/syndication_review_queue_v1_provisional.csv")
OUT_MD = Path("news_collection/syndication_summary_v1_provisional.md")

FIELDS = ["article_id_a", "article_id_b", "publisher_a", "publisher_b",
          "pub_date_a", "pub_date_b", "capture_a", "capture_b",
          "jaccard", "containment", "shared_paragraphs",
          "shared_paragraph_sample", "attribution_a", "attribution_b",
          "byline_match", "classification", "direction",
          "direction_confidence", "review_reason", "rule_version"]


def main() -> None:
    arts = {}
    for line in LAYER.open():
        a = json.loads(line)
        arts[a["article_id"]] = a
    captures = {r["article_id"]: r["wayback_capture_ts"]
                for r in csv.DictReader(URL_MAP.open())}
    pub_dates = {r["article_id"]: r["effective_date"]
                 for r in csv.DictReader(DATES.open())
                 if r.get("date_status") == "usable"}

    def evidence(aid: str) -> dict:
        art = arts.get(aid, {})
        return {"article_id": aid,
                "source": art.get("source_name", ""),
                "body": art.get("body_text", ""),
                "paragraphs": art.get("body_paragraphs", []),
                "author": (art.get("author_text") or "").strip(),
                "pub_date": pub_dates.get(aid, ""),
                "capture_ts": captures.get(aid, "")}

    rels, skipped_same_publisher = [], 0
    for p in csv.DictReader(PAIRS.open()):
        if p["source_a"] == p["source_b"]:
            skipped_same_publisher += 1     # Step 5's inbox, not ours
            continue
        rels.append(classify_pair(
            p, evidence(p["article_id_a"]), evidence(p["article_id_b"])))

    families = build_families(rels)

    cls_counts = Counter(r["classification"] for r in rels)
    directed = sum(1 for r in rels if r["direction"] != "undirected")
    review_rows = [r for r in rels
                   if r["classification"] in ("manual_review",
                                              "insufficient_evidence")]

    with OUT_REL.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(rels)
    with OUT_FAM.open("w") as fh:
        for f in families:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    with OUT_REVIEW.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(review_rows)

    OUT_MD.write_text(
        "# Syndication identification - Step 4 summary (v1 provisional)\n\n"
        f"* rules: `{RULE_VERSION}`\n"
        f"* cross-publisher pairs evaluated: **{len(rels)}** "
        f"({skipped_same_publisher} same-publisher pairs deferred to "
        "Step 5 as update candidates)\n"
        f"* classifications: {dict(cls_counts)}\n"
        f"* syndication families: {len(families)}\n"
        f"* directed links: {directed} (direction requires attribution "
        "plus consistent chronology; capture order alone never decides)\n"
        f"* review queue: {len(review_rows)} rows\n\n"
        "Shared facts, quotations and election results never constitute "
        "syndication evidence; wholesale paragraph reuse, attribution "
        "markers and byline matches do. No record was deleted or "
        "merged, and Step 1-3 identifiers are untouched.\n")

    print(f"{len(rels)} cross-publisher pairs -> {OUT_REL} "
          f"({skipped_same_publisher} same-publisher deferred)")
    print("classifications:", dict(cls_counts))
    print(f"families: {len(families)} | directed links: {directed}")
    print(f"review queue: {len(review_rows)} -> {OUT_REVIEW}")


if __name__ == "__main__":
    main()
