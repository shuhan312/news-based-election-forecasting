"""Phase 5 / Step 6 runner: duplicate-cluster validation over the
frozen corpus snapshot.

Reads every Step 1-5 output (read-only), assembles the typed evidence
graph, runs the conflict rules and component validation from
cluster_validation.py, and writes the validated provisional families.

Edge sources:

    Step 1  exact-duplicate clusters        -> exact_duplicate edges
    Step 2  multi-member canonical-URL groups -> same_canonical_url
    Step 3  near-duplicate pair table       -> near_duplicate edges
            (+ the human resolutions table as review status)
    Step 4  syndication relationships       -> syndication edges
    Step 5  version relationships           -> version edges
            (+ the Step 5 resolutions table as review status)

Temporal fields per article come verbatim from Step 5's availability
table and are copied through - validation never rewrites them.

Outputs (versioned _v1_provisional, all tracked):

    news_collection/validated_duplicate_relationships_v1_provisional.csv
    news_collection/validated_duplicate_clusters_v1_provisional.jsonl
    news_collection/duplicate_cluster_conflicts_v1_provisional.csv
    news_collection/duplicate_cluster_review_queue_v1_provisional.csv
    news_collection/duplicate_cluster_validation_summary_v1_provisional.md

Usage:
    python3 -m src.dedup.build_cluster_validation
"""

import csv
import json
from collections import Counter
from pathlib import Path

from .cluster_validation import RULE_VERSION, validate_graph

LAYER = Path("news_collection/normalised_text_layer_v1_provisional.jsonl")
EXACT = Path("news_collection/exact_duplicate_clusters_v1_provisional.jsonl")
URL_MAP = Path("news_collection/url_duplicate_mapping_v1_provisional.csv")
ND_PAIRS = Path("news_collection/near_duplicate_pairs_v1_provisional.csv")
ND_RES = Path(
    "news_collection/near_duplicate_resolutions_v1_provisional.csv")
SYN = Path("news_collection/syndication_relationships_v1_provisional.csv")
VER = Path(
    "news_collection/article_version_relationships_v1_provisional.csv")
VER_RES = Path(
    "news_collection/article_version_resolutions_v1_provisional.csv")
AVAIL = Path("news_collection/"
             "article_version_temporal_availability_v1_provisional.csv")

OUT_REL = Path(
    "news_collection/validated_duplicate_relationships_v1_provisional.csv")
OUT_FAM = Path(
    "news_collection/validated_duplicate_clusters_v1_provisional.jsonl")
OUT_CONF = Path(
    "news_collection/duplicate_cluster_conflicts_v1_provisional.csv")
OUT_REVIEW = Path(
    "news_collection/duplicate_cluster_review_queue_v1_provisional.csv")
OUT_MD = Path("news_collection/"
              "duplicate_cluster_validation_summary_v1_provisional.md")

INPUT_REFS = ("layer=normalised-text-v1_provisional;"
              "exact=exact-dup-v1.0;url=url-canon-v1.0-2026-07-27;"
              "near-dup=near-dup-v1.0-2026-07-26;"
              "syndication=syndication-v1.0-2026-07-26;"
              "version=version-link-v1.0-2026-07-26")

# per-class edge confidence carried into the graph (descriptive - the
# conflict rules and thresholds do the actual work)
CONFIDENCE = {"exact_duplicate": "certain",
              "high_confidence_near_duplicate": "high",
              "partial_full_text_match": "high",
              "probable_near_duplicate": "medium",
              "identical_recapture": "certain",
              "minor_update": "high", "substantive_update": "high",
              "partial_to_full_version": "high",
              "archive_current_version": "high",
              "url_variant_probable_same_page": "medium"}

REL_FIELDS = ["article_id_a", "article_id_b", "edge_type", "source_step",
              "classification", "confidence", "jaccard", "containment",
              "disposition", "block_reason", "review_status",
              "human_decision", "rule_version", "input_refs"]

CONF_FIELDS = ["article_id_a", "article_id_b", "edge_type",
               "classification", "rule", "resolution", "rule_version"]


def main() -> None:
    arts_raw = {}
    for line in LAYER.open():
        a = json.loads(line)
        arts_raw[a["article_id"]] = a
    avail = {r["article_id"]: r for r in csv.DictReader(AVAIL.open())}
    articles = {aid: {
        "words": len((a.get("body_text") or "").split()),
        "quality": a.get("quality_status", ""),
        "pub_date": avail.get(aid, {}).get("published_at", ""),
        "availability_status": avail.get(aid, {}).get(
            "availability_status", ""),
        "available_from": avail.get(aid, {}).get("version_available_at")
        or avail.get(aid, {}).get("available_lower_bound", "")}
        for aid, a in arts_raw.items()}

    nd_res = {frozenset((r["article_id_a"], r["article_id_b"])):
              r["decision"] for r in csv.DictReader(ND_RES.open())}
    ver_res = {frozenset((r["article_id_a"], r["article_id_b"])):
               r["decision"] for r in csv.DictReader(VER_RES.open())}

    def edge(a, b, etype, step, cls, evidence, resolutions):
        pair = frozenset((a, b))
        decision = resolutions.get(pair, "")
        return {"a": min(a, b), "b": max(a, b), "edge_type": etype,
                "source_step": step, "classification": cls,
                "confidence": CONFIDENCE.get(cls, "low"),
                "evidence": evidence,
                "review_status": "human_resolved" if decision else "",
                "human_decision": decision}

    edges = []
    # Step 1 - exact-duplicate clusters (pairwise edges per cluster)
    for line in EXACT.open():
        c = json.loads(line)
        ms = sorted(c["member_ids"])
        for i, x in enumerate(ms):
            for y in ms[i + 1:]:
                edges.append(edge(x, y, "exact_duplicate", "step1",
                                  "exact_duplicate", {"jaccard": 1.0},
                                  {}))
    # Step 2 - multi-member canonical-URL groups
    by_group = {}
    for r in csv.DictReader(URL_MAP.open()):
        if int(r["group_size"]) > 1:
            by_group.setdefault(r["group_id"], []).append(r)
    for rows in by_group.values():
        ids = sorted(x["article_id"] for x in rows)
        rel = rows[0]["relationship"]
        for i, x in enumerate(ids):
            for y in ids[i + 1:]:
                edges.append(edge(x, y, "same_canonical_url", "step2",
                                  rel, {}, {}))
    # Step 3 - every near-duplicate pair, linking or not
    for r in csv.DictReader(ND_PAIRS.open()):
        edges.append(edge(
            r["article_id_a"], r["article_id_b"], "near_duplicate",
            "step3", r["classification"],
            {"jaccard": r["jaccard"], "containment": r["containment"]},
            nd_res))
    # Step 4 - syndication relationships (their own layer)
    for r in csv.DictReader(SYN.open()):
        edges.append(edge(
            r["article_id_a"], r["article_id_b"], "syndication",
            "step4", r["classification"],
            {"jaccard": r["jaccard"], "containment": r["containment"]},
            {}))
    # Step 5 - version relationships
    for r in csv.DictReader(VER.open()):
        edges.append(edge(
            r["article_id_a"], r["article_id_b"], "version", "step5",
            r["classification"],
            {"jaccard": r["jaccard"], "containment": r["containment"]},
            ver_res))

    result = validate_graph(articles, edges)

    # ---- write outputs ----------------------------------------------
    rel_rows = []
    for e in result["relationships"]:
        ev = e.get("evidence") or {}
        rel_rows.append({
            "article_id_a": e["a"], "article_id_b": e["b"],
            "edge_type": e["edge_type"], "source_step": e["source_step"],
            "classification": e["classification"],
            "confidence": e["confidence"],
            "jaccard": ev.get("jaccard", ""),
            "containment": ev.get("containment", ""),
            "disposition": e["disposition"],
            "block_reason": e.get("block_reason", ""),
            "review_status": e.get("review_status", ""),
            "human_decision": e.get("human_decision", ""),
            "rule_version": RULE_VERSION, "input_refs": INPUT_REFS})
    with OUT_REL.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REL_FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(rel_rows)

    with OUT_FAM.open("w") as fh:
        for f in result["families"]:
            fh.write(json.dumps({**f, "input_refs": INPUT_REFS},
                                ensure_ascii=False) + "\n")

    with OUT_CONF.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CONF_FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(result["conflicts"])

    review = [f for f in result["families"]
              if f["validation_status"] == "review"]
    with OUT_REVIEW.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "family_id", "layer", "family_type", "members",
            "unsupported_pairs", "contradictions", "warnings",
            "rule_version"], lineterminator="\n")
        w.writeheader()
        for f in review:
            w.writerow({"family_id": f["family_id"], "layer": f["layer"],
                        "family_type": f["family_type"],
                        "members": ";".join(f["members"]),
                        "unsupported_pairs": ";".join(
                            f["unsupported_pairs"]),
                        "contradictions": ";".join(f["contradictions"]),
                        "warnings": ";".join(f["warnings"]),
                        "rule_version": RULE_VERSION})

    # ---- reconciliation ---------------------------------------------
    status = Counter(s["status"]
                     for s in result["article_status"].values())
    in_fam = sum(1 for s in result["article_status"].values()
                 if s["status"] == "in_validated_family")
    assert len(result["article_status"]) == len(arts_raw), \
        "every Phase 4 article must carry an explicit status"
    assert len(rel_rows) == len(edges), \
        "every input relationship must be retained in the output"

    disp = Counter(e["disposition"] for e in result["relationships"])
    ftypes = Counter(f["family_type"] for f in result["families"])
    fstatus = Counter(f["validation_status"] for f in result["families"])

    OUT_MD.write_text(
        "# Duplicate-cluster validation - Step 6 summary "
        "(v1 provisional)\n\n"
        f"* rules: `{RULE_VERSION}`\n"
        f"* authoritative inputs: `{INPUT_REFS}`\n"
        f"* evidence graph: {len(arts_raw)} articles, "
        f"{len(edges)} typed edges; dispositions {dict(disp)}\n"
        f"* validated families: {len(result['families'])} "
        f"by type {dict(ftypes)}; status {dict(fstatus)}\n"
        f"* conflict-rule applications: {len(result['conflicts'])}\n"
        f"* review queue: {len(review)} families\n"
        f"* article status: {dict(status)} "
        f"(reconciled: {in_fam} in families + "
        f"{status['independent_article']} independent = "
        f"{len(arts_raw)})\n\n"
        "Relationship types were never flattened; blocked and "
        "superseded edges remain recorded with their blocking rule. "
        "Syndication stays a separate layer from same-article "
        "families. Member temporal availability is copied verbatim "
        "from Step 5 - validation altered no availability decision "
        "and no prediction-window flag. No record was deleted, "
        "merged or suppressed.\n")

    print(f"{len(edges)} edges -> {OUT_REL} | dispositions {dict(disp)}")
    print(f"families: {dict(ftypes) or 0} | status {dict(fstatus)}")
    print(f"conflicts: {len(result['conflicts'])} | review: {len(review)}")
    print(f"articles: {dict(status)}")


if __name__ == "__main__":
    main()
