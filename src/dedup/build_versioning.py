"""Phase 5 / Step 5 runner: version linking and temporal availability
over the frozen corpus snapshot.

Candidate selection (the specification's evidence sources, applied to
what this corpus actually contains):

    * Step 3 same-publisher pairs classified at duplicate grade
      (high_confidence / probable / partial_full_text_match) - the
      inbox Step 4 deliberately deferred here;
    * Step 2 multi-member canonical-URL groups (same URL, different
      body hashes = the same page captured at different moments);
    * pairs already resolved by a human in the Step 3 resolutions
      table are EXCLUDED - a signed not_near_duplicate decision is
      not reopened by an automatic step.

Cross-publisher pairs are out of scope by construction (Step 4's
closed question); the syndication relationships file is read only to
assert no candidate pair also carries a syndication relationship, so
syndicated copies can never convert into version chains.

Inputs (read-only): the Phase 4 layer (titles, standfirsts, bodies,
paragraphs, authors, final body hashes, election ids), Step 3 pair
table + resolutions, Step 2 URL mapping (canonical URLs,
archive/retrieval timestamps), upstream effective dates
(publication). Explicit updated_at metadata does not exist in the v1
layer; the update_ts columns are recorded absent rather than filled
from another timestamp kind.

Outputs (versioned _v1_provisional, all tracked):

    news_collection/article_version_relationships_v1_provisional.csv
    news_collection/article_version_families_v1_provisional.jsonl
    news_collection/article_version_temporal_availability_v1_provisional.csv
        one row per Phase 4 article: explicit version-processing
        status, availability decision and per-window flags - the
        leakage-safety surface downstream steps consume
    news_collection/article_version_review_queue_v1_provisional.csv
    news_collection/article_version_summary_v1_provisional.md

Usage:
    python3 -m src.dedup.build_versioning
"""

import csv
import json
from collections import Counter
from pathlib import Path

from .versioning import (PREDICTION_WINDOWS, RULE_VERSION, availability,
                         build_version_families, classify_version_pair,
                         temporal_profile, window_flags)

LAYER = Path("news_collection/normalised_text_layer_v1_provisional.jsonl")
PAIRS = Path("news_collection/near_duplicate_pairs_v1_provisional.csv")
RESOLUTIONS = Path(
    "news_collection/near_duplicate_resolutions_v1_provisional.csv")
URL_MAP = Path("news_collection/url_duplicate_mapping_v1_provisional.csv")
DATES = Path("news_collection/effective_dates.csv")
SYN = Path("news_collection/syndication_relationships_v1_provisional.csv")

OUT_REL = Path(
    "news_collection/article_version_relationships_v1_provisional.csv")
OUT_FAM = Path(
    "news_collection/article_version_families_v1_provisional.jsonl")
OUT_AVAIL = Path("news_collection/"
                 "article_version_temporal_availability_v1_provisional.csv")
OUT_REVIEW = Path(
    "news_collection/article_version_review_queue_v1_provisional.csv")
OUT_MD = Path(
    "news_collection/article_version_summary_v1_provisional.md")

DUP_GRADE = {"high_confidence_near_duplicate", "probable_near_duplicate",
             "partial_full_text_match"}

# Authoritative input versions referenced in every output (the
# specification's input-version references).
INPUT_REFS = ("layer=normalised-text-v1_provisional;"
              "pairs=near-dup-v1.0-2026-07-26;"
              "url=url-canon-v1.0-2026-07-27;"
              "syndication=syndication-v1.0-2026-07-26")

REL_FIELDS = ["article_id_a", "article_id_b", "publisher", "byline_match",
              "original_url_a", "original_url_b",
              "canonical_url_a", "canonical_url_b", "same_canonical_url",
              "body_hash_a", "body_hash_b",
              "pub_date_a", "pub_date_b", "update_ts_a", "update_ts_b",
              "capture_a", "capture_b", "retrieved_a", "retrieved_b",
              "jaccard", "containment", "title_sim", "seq_ratio",
              "length_ratio", "paragraphs_added", "paragraphs_deleted",
              "paragraphs_modified", "paragraphs_common",
              "added_sample", "deleted_sample", "modified_sample",
              "title_changed", "standfirst_changed", "numbers_changed",
              "quotes_changed", "word_count_diff",
              "classification", "relationship_confidence",
              "chronology", "chronology_basis",
              "availability_status_a", "availability_status_b",
              "available_from_a", "available_from_b",
              "review_reason", "rule_version", "input_refs"]

AVAIL_FIELDS = (["article_id", "election_id", "publisher",
                 "version_processing_status", "version_family_id",
                 "version_sequence",
                 "published_at", "published_tz_status",
                 "published_confidence",
                 "updated_at", "updated_resolution_status",
                 "retrieved_at", "archived_at", "first_observed_at",
                 "availability_status", "version_available_at",
                 "available_lower_bound", "available_upper_bound"]
                + [f"in_window_{w}" for w in PREDICTION_WINDOWS]
                + ["warning_flags", "rule_version", "input_refs"])


def main() -> None:
    arts = {}
    for line in LAYER.open():
        a = json.loads(line)
        arts[a["article_id"]] = a
    url_rows = {r["article_id"]: r
                for r in csv.DictReader(URL_MAP.open())}
    pub_dates = {r["article_id"]: r["effective_date"]
                 for r in csv.DictReader(DATES.open())
                 if r.get("date_status") == "usable"}
    resolved = {frozenset((r["article_id_a"], r["article_id_b"]))
                for r in csv.DictReader(RESOLUTIONS.open())}
    syndicated = {frozenset((r["article_id_a"], r["article_id_b"]))
                  for r in csv.DictReader(SYN.open())}

    def evidence(aid: str) -> dict:
        art, u = arts.get(aid, {}), url_rows.get(aid, {})
        return {"article_id": aid,
                "source": art.get("source_name", ""),
                "election_id": art.get("election_id", ""),
                "title": art.get("title", ""),
                "standfirst": art.get("standfirst", ""),
                "body": art.get("body_text", ""),
                "paragraphs": art.get("body_paragraphs", []),
                "author": (art.get("author_text") or "").strip(),
                "body_hash": (art.get("hashes") or {}).get("final_body", ""),
                "original_url": u.get("original_url", ""),
                "canonical_url": u.get("canonical_url", ""),
                "pub_date": pub_dates.get(aid, ""),
                "update_ts": "",        # absent in the v1 layer
                "capture_ts": u.get("wayback_capture_ts", ""),
                "retrieved_at": u.get("retrieved_at", "")}

    # ---- candidate generation ---------------------------------------
    cands: set[frozenset] = set()
    for p in csv.DictReader(PAIRS.open()):
        pair = frozenset((p["article_id_a"], p["article_id_b"]))
        if p["source_a"] != p["source_b"]:
            continue                       # Step 4's territory, closed
        if pair in resolved:
            continue                       # human decision stands
        if p["classification"] in DUP_GRADE or "same_url_group" in p["flags"]:
            cands.add(pair)

    by_group: dict[str, list[str]] = {}
    for aid, r in url_rows.items():
        if int(r["group_size"]) > 1:
            by_group.setdefault(r["group_id"], []).append(aid)
    for ids in by_group.values():
        for i, x in enumerate(sorted(ids)):
            for y in sorted(ids)[i + 1:]:
                if frozenset((x, y)) not in resolved:
                    cands.add(frozenset((x, y)))

    # syndicated copies must never become same-publisher version chains
    overlap = cands & syndicated
    assert not overlap, f"candidate pair also syndicated: {overlap}"

    rels = []
    for pair in sorted(cands, key=sorted):
        x, y = sorted(pair)
        r = classify_version_pair(evidence(x), evidence(y))
        r["input_refs"] = INPUT_REFS
        rels.append(r)

    ev_map = {aid: evidence(aid)
              for r in rels for aid in (r["article_id_a"], r["article_id_b"])}
    families = build_version_families(rels, ev_map)
    fam_of = {m["article_id"]: (f["family_id"], m["version_sequence"])
              for f in families for m in f["members"]}

    # ---- per-article temporal availability (every Phase 4 article) --
    avail_rows = []
    for aid in sorted(arts):
        ev = evidence(aid)
        t = temporal_profile(ev)
        av = availability(ev)
        flags = window_flags(ev, ev["election_id"])
        warn = []
        if arts[aid].get("quality_status") == "not_usable":
            warn.append("layer_not_usable")
        if av["availability_status"] in ("availability_uncertain",
                                         "not_temporally_usable"):
            warn.append("no_usable_temporal_evidence")
        fam_id, seq = fam_of.get(aid, ("", None))
        avail_rows.append({
            "article_id": aid, "election_id": ev["election_id"],
            "publisher": ev["source"],
            "version_processing_status": "in_version_family" if fam_id
            else "no_version_candidates",
            "version_family_id": fam_id,
            "version_sequence": seq if seq is not None else "",
            "published_at": t["published_at"]["value"],
            "published_tz_status": t["published_at"]["tz_status"],
            "published_confidence": t["published_at"]["confidence"],
            "updated_at": t["updated_at"]["value"],
            "updated_resolution_status":
                t["updated_at"]["resolution_status"],
            "retrieved_at": t["retrieved_at"]["value"],
            "archived_at": t["archived_at"]["value"],
            "first_observed_at": t["first_observed_at"]["value"],
            **av, **flags,
            "warning_flags": ";".join(warn),
            "rule_version": RULE_VERSION, "input_refs": INPUT_REFS})

    # ---- reconciliation and reporting -------------------------------
    assert len(avail_rows) == len(arts), "availability table must cover " \
        "every Phase 4 article exactly once"

    cls_counts = Counter(r["classification"] for r in rels)
    ordered_fams = sum(1 for f in families if f["ordered"])
    review_rows = [r for r in rels
                   if r["classification"] in ("manual_review",
                                              "ambiguous_version_relationship")
                   or r["review_reason"]]
    avail_counts = Counter(r["availability_status"] for r in avail_rows)
    confirmed_windows = Counter()
    for r in avail_rows:
        for w in PREDICTION_WINDOWS:
            confirmed_windows[r[f"in_window_{w}"]] += 1

    with OUT_REL.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REL_FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(rels)
    with OUT_FAM.open("w") as fh:
        for f in families:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    with OUT_AVAIL.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=AVAIL_FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(avail_rows)
    with OUT_REVIEW.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REL_FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(review_rows)

    OUT_MD.write_text(
        "# Article version linking - Step 5 summary (v1 provisional)\n\n"
        f"* rules: `{RULE_VERSION}`\n"
        f"* authoritative inputs: `{INPUT_REFS}`\n"
        f"* candidate pairs evaluated: **{len(rels)}** (same-publisher "
        "duplicate-grade + multi-member URL groups; human-resolved "
        "pairs excluded; zero overlap with syndication relationships "
        "asserted)\n"
        f"* classifications: {dict(cls_counts)}\n"
        f"* version families: {len(families)} "
        f"({ordered_fams} chronologically ordered, "
        f"{len(families) - ordered_fams} unordered and flagged)\n"
        f"* review queue: {len(review_rows)} rows\n"
        f"* temporal availability over {len(avail_rows)} articles: "
        f"{dict(avail_counts)}\n"
        f"* window-flag distribution (all windows pooled): "
        f"{dict(confirmed_windows)}\n\n"
        "The six temporal fields are carried separately and never "
        "substituted; explicit updated_at metadata does not exist in "
        "the v1 layer and is recorded absent. Version order uses "
        "publication dates only. Each version's availability is its "
        "own capture evidence or a preserved [publication, "
        "first-observation] interval - exact times are never invented, "
        "and yes_publication_claim_only window flags are reserved for "
        "downstream sensitivity testing, never silent inclusion. No "
        "version was deleted or overwritten; Step 1-4 outputs are "
        "untouched.\n")

    print(f"{len(rels)} candidate pairs -> {OUT_REL}")
    print("classifications:", dict(cls_counts))
    print(f"families: {len(families)} ({ordered_fams} ordered) | "
          f"review queue: {len(review_rows)}")
    print(f"availability over {len(avail_rows)} articles:",
          dict(avail_counts))


if __name__ == "__main__":
    main()
