"""Phase 5 / Step 8 runner: consolidate Steps 1-7 and freeze the
provisional duplicate mapping layer.

Reads every Phase 5 output (read-only), assembles the one-row-per-
article layer via mapping_layer.py, validates integrity, and freezes
four outputs behind the freeze guard:

    news_collection/duplicate_mapping_layer_v1_provisional.csv
    news_collection/duplicate_mapping_manifest_v1_provisional.json
    news_collection/duplicate_mapping_audit_v1_provisional.md
    news_collection/duplicate_mapping_review_queue_v1_provisional.csv

Stage M compatibility: retrieval is still running, so this snapshot
deliberately does NOT claim full corpus coverage. The audit file
documents what is covered, what is missing and the incremental
procedure: new articles append through Phase 4 -> Phase 5 Steps 1-7
-> a v2 release alongside (never over) this v1 snapshot.

Determinism: no wall-clock timestamps anywhere - the manifest is
dated by the corpus SNAPSHOT_DATE and carries the git commit hash,
so a rerun at the same commit is byte-identical and the freeze guard
treats it as a no-op.

Usage:
    python3 -m src.dedup.build_mapping_layer
"""

import csv
import io
import json
import subprocess
from collections import Counter
from hashlib import sha256
from pathlib import Path

from .mapping_layer import (RULE_VERSION, SNAPSHOT_DATE, build_row,
                            freeze_write, validate_mapping)

LAYER = Path("news_collection/normalised_text_layer_v1_provisional.jsonl")
CANON = Path(
    "news_collection/canonical_article_mapping_v1_provisional.csv")
CLUSTERS = Path(
    "news_collection/validated_duplicate_clusters_v1_provisional.jsonl")
VALID_REL = Path(
    "news_collection/validated_duplicate_relationships_v1_provisional.csv")
VER_REL = Path(
    "news_collection/article_version_relationships_v1_provisional.csv")
SYN = Path("news_collection/syndication_relationships_v1_provisional.csv")
URL_MAP = Path("news_collection/url_duplicate_mapping_v1_provisional.csv")
AVAIL = Path("news_collection/"
             "article_version_temporal_availability_v1_provisional.csv")

OUT_CSV = Path(
    "news_collection/duplicate_mapping_layer_v1_provisional.csv")
OUT_MANIFEST = Path(
    "news_collection/duplicate_mapping_manifest_v1_provisional.json")
OUT_AUDIT = Path(
    "news_collection/duplicate_mapping_audit_v1_provisional.md")
OUT_REVIEW = Path(
    "news_collection/duplicate_mapping_review_queue_v1_provisional.csv")

INPUT_REFS = ("layer=normalised-text-v1_provisional;"
              "url=url-canon-v1.0-2026-07-27;"
              "near-dup=near-dup-v1.0-2026-07-26;"
              "syndication=syndication-v1.0-2026-07-26;"
              "version=version-link-v1.0-2026-07-26;"
              "clusters=cluster-validation-v1.0-2026-07-26;"
              "canonical=canonical-v1.0-2026-07-26")

FIELDS = ["article_id", "canonical_article_id", "duplicate_family_id",
          "relationship_status", "family_type", "canonical_status",
          "syndication_status", "version_status", "source_article_id",
          "temporal_validity_status", "downstream_usage_status",
          "review_status", "originating_steps", "evidence_ref",
          "best_similarity", "selection_evidence", "available_from",
          "review_flags", "rule_version", "input_refs"]


def git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
            cwd=Path(__file__).resolve().parent).stdout.strip()
    except Exception:
        return "unavailable"


def main() -> None:
    article_ids = set()
    for line in LAYER.open():
        article_ids.add(json.loads(line)["article_id"])
    canon = {r["article_id"]: r for r in csv.DictReader(CANON.open())}
    avail = {r["article_id"]: r for r in csv.DictReader(AVAIL.open())}
    families = [json.loads(line) for line in CLUSTERS.open()]
    fam_of = {aid: f for f in families for aid in f["members"]}

    # per-article helper indexes -------------------------------------
    ver_class: dict[str, set] = {}
    same_url_pair: set[str] = set()
    for r in csv.DictReader(VER_REL.open()):
        for aid in (r["article_id_a"], r["article_id_b"]):
            ver_class.setdefault(aid, set()).add(r["classification"])
            if r["same_canonical_url"] == "True":
                same_url_pair.add(aid)
    syn_member: dict[str, str] = {}
    for r in csv.DictReader(SYN.open()):
        for aid in (r["article_id_a"], r["article_id_b"]):
            syn_member[aid] = r["classification"]
    steps_of: dict[str, set] = {}
    best_sim: dict[str, float] = {}
    for r in csv.DictReader(VALID_REL.open()):
        for aid in (r["article_id_a"], r["article_id_b"]):
            steps_of.setdefault(aid, set()).add(r["source_step"])
            try:
                s = max(float(r["jaccard"] or 0),
                        float(r["containment"] or 0))
            except ValueError:
                s = 0.0
            best_sim[aid] = max(best_sim.get(aid, 0.0), s)
    rows = []
    for aid in sorted(article_ids):
        c = canon.get(aid, {})
        f = fam_of.get(aid)
        in_family = f is not None
        held = c.get("canonical_status") \
            == "canonical_uncertain_manual_review"
        is_canonical = in_family and not held \
            and c.get("canonical_article_id") == aid
        version_status = "single_version"
        if aid in ver_class:
            version_status = ";".join(sorted(ver_class[aid]))
        ctx = {"in_family": in_family,
               "family_id": f["family_id"] if f else "",
               "family_type": f["family_type"] if f
               else "independent_articles",
               "is_canonical": is_canonical, "held": held,
               "same_url_archive": aid in same_url_pair,
               "canonical_article_id": c.get("canonical_article_id",
                                             aid) or aid,
               "canonical_status": c.get("canonical_status", ""),
               "syndication_status": syn_member.get(aid,
                                                    "not_syndicated"),
               "version_status": version_status,
               "temporal_validity_status":
                   c.get("temporal_validity_status")
                   or avail.get(aid, {}).get("availability_status", ""),
               "originating_steps": ";".join(sorted(
                   steps_of.get(aid, {"step3"})))
               if aid in steps_of else "blocking_steps_only",
               "best_similarity": f"{best_sim[aid]:.4f}"
               if aid in best_sim else "",
               "selection_evidence": c.get("selection_evidence", ""),
               "available_from": avail.get(aid, {}).get(
                   "version_available_at")
               or avail.get(aid, {}).get("available_lower_bound", ""),
               "review_flags": ";".join(f["warnings"]) if f else "",
               "input_refs": INPUT_REFS}
        rows.append(build_row(aid, ctx))

    validate_mapping(rows, article_ids)

    # ---- serialise (in memory first - the freeze guard compares) ----
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader(); w.writerows(rows)
    csv_text = buf.getvalue()

    review_rows = [r for r in rows
                   if r["review_status"] == "review_required"]
    rbuf = io.StringIO()
    w = csv.DictWriter(rbuf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader(); w.writerows(review_rows)
    review_text = rbuf.getvalue()

    rel_counts = Counter(r["relationship_status"] for r in rows)
    usage_counts = Counter(r["downstream_usage_status"] for r in rows)
    edge_counts = Counter(r["source_step"] for r in
                          csv.DictReader(VALID_REL.open()))

    manifest = {
        "layer": "duplicate_mapping_layer_v1_provisional",
        "snapshot_date": SNAPSHOT_DATE,
        "rule_version": RULE_VERSION,
        "input_refs": INPUT_REFS,
        "code_version_git_head": git_head(),
        "inputs": {p.name: sha256(p.read_bytes()).hexdigest()
                   for p in [LAYER, CANON, CLUSTERS, VALID_REL,
                             VER_REL, SYN, URL_MAP, AVAIL]},
        "record_count": len(rows),
        "relationship_status_counts": dict(sorted(rel_counts.items())),
        "relationship_edge_counts_by_step":
            dict(sorted(edge_counts.items())),
        "family_count": len(families),
        "canonical_count": rel_counts["canonical_article"],
        "independent_count":
            rel_counts["non_duplicate_independent_article"],
        "evidence_only_count": sum(
            v for k, v in rel_counts.items()
            if k in ("archive_version", "updated_version",
                     "exact_duplicate", "near_duplicate",
                     "syndicated_copy")),
        "review_count": len(review_rows),
        "layer_sha256": sha256(csv_text.encode()).hexdigest(),
        "coverage_note": ("Stage M retrieval incomplete - this is a "
                          "provisional snapshot, not the final "
                          "corpus freeze"),
    }
    manifest_text = json.dumps(manifest, indent=2,
                               ensure_ascii=False) + "\n"

    audit_text = (
        "# Duplicate mapping layer - Step 8 audit (v1 provisional)\n\n"
        f"* snapshot date: {SNAPSHOT_DATE} | rules: `{RULE_VERSION}` "
        f"| git: `{manifest['code_version_git_head']}`\n"
        f"* authoritative inputs: `{INPUT_REFS}` (sha256 per file in "
        "the manifest)\n"
        f"* records: {len(rows)} (one per Phase 4 article; "
        "reconciled)\n"
        f"* relationship statuses: {dict(sorted(rel_counts.items()))}\n"
        f"* downstream usage: {dict(sorted(usage_counts.items()))}\n"
        f"* review queue: {len(review_rows)} rows\n\n"
        "## Coverage (do not mistake for the final corpus)\n\n"
        "Included: Stage A-L collection plus the completed portion of "
        "the Stage M windowed re-sweep, processed through Phase 4 "
        "normalisation and Phase 5 Steps 1-7. NOT included: the "
        "remaining Stage M queries (~600) still to run. This layer "
        "therefore freezes the duplicate-resolution STATE of the "
        "current snapshot, not the dissertation corpus.\n\n"
        "## Incremental update procedure (v2 and later)\n\n"
        "1. new Stage M articles land as raw records and pass Phase 4 "
        "into a v2 normalised layer (v1 untouched);\n"
        "2. Phase 5 Steps 1-7 rerun over the enlarged corpus - "
        "content-hash-derived family ids keep unchanged families "
        "stable, and only families whose membership actually changes "
        "get new ids;\n"
        "3. the rebuilt mapping freezes as "
        "duplicate_mapping_layer_v2_provisional ALONGSIDE this file; "
        "the freeze guard refuses any in-place rewrite of v1;\n"
        "4. downstream work pins the layer version it consumed.\n\n"
        "Relationship types remain separate columns throughout; "
        "pairwise evidence lives in the Step 1-7 outputs referenced "
        "by family id. No article was deleted, no record merged, and "
        "Phase 6 (LLM extraction) was not started.\n")

    results = {str(OUT_CSV): freeze_write(OUT_CSV, csv_text),
               str(OUT_MANIFEST): freeze_write(OUT_MANIFEST,
                                               manifest_text),
               str(OUT_AUDIT): freeze_write(OUT_AUDIT, audit_text),
               str(OUT_REVIEW): freeze_write(OUT_REVIEW, review_text)}

    print(f"{len(rows)} mapping rows | statuses "
          f"{dict(sorted(rel_counts.items()))}")
    print(f"usage {dict(sorted(usage_counts.items()))} | "
          f"review {len(review_rows)}")
    print("freeze:", results)


if __name__ == "__main__":
    main()
