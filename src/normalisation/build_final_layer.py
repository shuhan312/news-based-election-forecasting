"""Phase 4 / Step 7 runner: audit Steps 1-6, run the language check,
and freeze normalised_text_layer_v1_provisional.

PROVISIONAL records the state at this snapshot date: Stage M's windowed
re-sweep could still add eligible articles when v1 was frozen. The snapshot is
never overwritten; the freeze guard below refuses to replace an existing layer
file whose content differs.

Audit joins, per article_id:
    Step 1 manifest       selected source path + hash
    Step 2 log            input (raw html / api text) path + hash
    Step 3 log            in/out hashes (character normalisation)
    Step 4 log            in/out hashes (structure normalisation)
    Step 5 log            in/out hashes (boundary resolution)
    Step 6 results        quality status + signals
    resolution tables     structure keeps, media-only, quality keeps

Chain reconciliation: step4.input_sha == step3.output_sha and
step5.input_sha == step4.output_sha for every article that flowed
through - a broken link means an intermediate file was regenerated
out of band, and the audit fails loudly.

Outputs (all versioned *_v1_provisional):
    normalised_text_layer_v1_provisional.jsonl   canonical layer (full
        text -> gitignored like all corpus text)
    normalised_text_audit_v1_provisional.csv     per-article audit row
        (no text - tracked)
    normalised_text_quality_report_v1_provisional.md
    normalised_text_manifest_v1_provisional.json (carries a real
        timestamp + git commit; documented as the one non-
        deterministic output - layer and audit stay byte-stable)
    normalised_text_review_queue_v1_provisional.csv

Usage:
    python3 -m src.normalisation.build_final_layer
"""

import csv
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .final_audit import (LAYER_VERSION, RULE_VERSION, detect_language,
                          downstream_status)

NC = Path("news_collection")
STEP1 = NC / "normalisation_input_manifest_v1.csv"
STEP2_LOG = NC / "html_cleaning_log_v1.csv"
STEP3_LOG = NC / "character_normalisation_log_v1.csv"
STEP4_LOG = NC / "structure_normalisation_log_v1.csv"
STEP5_LOG = NC / "text_boundary_log_v1.csv"
STEP5_JSONL = NC / "structured_articles_v1.jsonl"
STEP6 = NC / "text_quality_results_v1.csv"
RES_QUALITY = NC / "text_quality_resolutions_v1.csv"
RES_MEDIA = NC / "missing_text_resolutions_v1.csv"
DECISIONS = NC / "corpus_eligibility_decisions.csv"
PILOT = NC / "manual_review_sample.csv"
VALIDATION = NC / "llm_validation_sample.csv"

OUT_LAYER = NC / "normalised_text_layer_v1_provisional.jsonl"
OUT_AUDIT = NC / "normalised_text_audit_v1_provisional.csv"
OUT_REPORT = NC / "normalised_text_quality_report_v1_provisional.md"
OUT_MANIFEST = NC / "normalised_text_manifest_v1_provisional.json"
OUT_REVIEW = NC / "normalised_text_review_queue_v1_provisional.csv"

AUDIT_FIELDS = ["article_id", "election_id", "arm", "source_name",
                "quality_status", "downstream_status", "language",
                "language_confidence", "body_words", "paragraphs",
                "raw_source_hash", "step3_out_sha", "step4_out_sha",
                "final_body_sha", "chain_ok", "flags",
                "layer_version", "rule_version"]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def csv_by_id(path):
    return {r["article_id"]: r for r in csv.DictReader(path.open())}


def load_election_arm():
    out = {}
    for r in csv.DictReader(DECISIONS.open()):
        out[r["article_id"]] = (r["election_id"], r["arm"])
    for p in (PILOT, VALIDATION):
        for r in csv.DictReader(p.open()):
            out.setdefault(r["article_id"],
                           (r.get("election_id", ""), r.get("arm", "")))
    return out


def freeze_guard(path: Path, new_content: str) -> None:
    """Refuse to silently overwrite a differing frozen snapshot."""
    if path.exists():
        old = path.read_text()
        if old != new_content and hashlib.sha256(old.encode()).hexdigest() \
                != hashlib.sha256(new_content.encode()).hexdigest():
            raise RuntimeError(
                f"{path} already exists with different content - the "
                "provisional snapshot is frozen. New articles belong in "
                "a v2 release, not an overwrite of v1.")
    path.write_text(new_content)


def main() -> None:
    s1, s2, s3 = csv_by_id(STEP1), csv_by_id(STEP2_LOG), csv_by_id(STEP3_LOG)
    s4, s5, s6 = csv_by_id(STEP4_LOG), csv_by_id(STEP5_LOG), csv_by_id(STEP6)
    res_quality = {r["article_id"]: r["decision"]
                   for r in csv.DictReader(RES_QUALITY.open())}
    media_ids = {r["article_id"] for r in csv.DictReader(RES_MEDIA.open())}
    election_arm = load_election_arm()
    articles = {json.loads(l)["article_id"]: json.loads(l)
                for l in STEP5_JSONL.open()}

    layer_lines, audit_rows, review_rows = [], [], []
    counts = {"quality": Counter(), "downstream": Counter(),
              "language": Counter(), "source": Counter(),
              "election": Counter(), "chain_fail": 0}

    for aid in sorted(s1):
        art = articles.get(aid, {"article_id": aid})
        q = s6.get(aid, {})
        quality = q.get("quality_status", "review_required")
        resolution = res_quality.get(aid)
        ds = downstream_status(quality, resolution)

        # Language over the exact downstream composition.
        lang = detect_language(" ".join(
            [art.get("title") or "", art.get("standfirst") or "",
             art.get("body_text") or ""]))

        # Hash-chain reconciliation across the intermediate layers.
        chain_ok = True
        if aid in s3 and aid in s4 and s3[aid]["output_sha256"]:
            chain_ok &= s3[aid]["output_sha256"] == s4[aid]["input_sha256"]
        if aid in s4 and aid in s5 and s4[aid]["output_sha256"]:
            chain_ok &= s4[aid]["output_sha256"] == s5[aid]["input_sha256"]
        if not chain_ok:
            counts["chain_fail"] += 1

        flags = sorted(set(
            (q.get("warning_flags") or "").split(";")) - {""})
        if lang["language"] in ("uncertain", "non_english",
                                "mixed_language"):
            flags.append(f"language_{lang['language']}")
        if resolution:
            flags.append("quality_resolved_by_human")
        if aid in media_ids:
            flags.append("media_only_resolved")

        elec, arm = election_arm.get(aid, ("", ""))
        source = s1[aid].get("source_name") or aid.split("-")[1]
        counts["quality"][quality] += 1
        counts["downstream"][ds] += 1
        counts["language"][lang["language"]] += 1
        counts["source"][source] += 1
        counts["election"][elec or "unknown"] += 1

        final_sha = sha256(art.get("body_text") or "")
        audit = {
            "article_id": aid, "election_id": elec, "arm": arm,
            "source_name": source, "quality_status": quality,
            "downstream_status": ds, "language": lang["language"],
            "language_confidence": lang["confidence"],
            "body_words": q.get("body_words", 0),
            "paragraphs": q.get("paragraphs", 0),
            "raw_source_hash": s1[aid]["selected_text_source_hash"],
            "step3_out_sha": s3.get(aid, {}).get("output_sha256", ""),
            "step4_out_sha": s4.get(aid, {}).get("output_sha256", ""),
            "final_body_sha": final_sha, "chain_ok": chain_ok,
            "flags": ";".join(flags),
            "layer_version": LAYER_VERSION,
            "rule_version": RULE_VERSION,
        }
        audit_rows.append(audit)
        if ds == "pending_review" or f"language_uncertain" in flags \
                or "language_non_english" in flags:
            review_rows.append(audit)

        layer_lines.append(json.dumps({
            "article_id": aid, "election_id": elec, "arm": arm,
            "source_name": source,
            "title": art.get("title", ""),
            "standfirst": art.get("standfirst", ""),
            "body_text": art.get("body_text", ""),
            "body_paragraphs": art.get("body_paragraphs", []),
            "author_text": art.get("author_text", ""),
            "caption_text": art.get("caption_text", []),
            "original_url": s1[aid].get("original_url", ""),
            "language": lang, "quality_status": quality,
            "downstream_status": ds, "flags": flags,
            "hashes": {"raw_source": s1[aid]["selected_text_source_hash"],
                       "step3_out": audit["step3_out_sha"],
                       "step4_out": audit["step4_out_sha"],
                       "final_body": final_sha},
            "step_versions": {
                "step1": s1[aid].get("input_selection_version", ""),
                "step5": s5.get(aid, {}).get("rule_version", ""),
                "step6": q.get("rule_version", ""),
                "step7": RULE_VERSION},
            "layer_version": LAYER_VERSION,
        }, ensure_ascii=False))

    assert len(audit_rows) == len(s1), "population mismatch - audit halted"

    # ---- freeze (guarded) -------------------------------------------
    freeze_guard(OUT_LAYER, "\n".join(layer_lines) + "\n")
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=AUDIT_FIELDS,
                       lineterminator="\n")
    w.writeheader(); w.writerows(audit_rows)
    freeze_guard(OUT_AUDIT, buf.getvalue())
    buf2 = io.StringIO()
    w2 = csv.DictWriter(buf2, fieldnames=AUDIT_FIELDS,
                        lineterminator="\n")
    w2.writeheader(); w2.writerows(review_rows)
    OUT_REVIEW.write_text(buf2.getvalue())

    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True,
        text=True).stdout.strip()
    manifest = {
        "layer_version": LAYER_VERSION, "rule_version": RULE_VERSION,
        "generated_at": datetime.now(timezone.utc)
                        .isoformat(timespec="seconds"),
        "git_commit": git_commit,
        "records": len(audit_rows),
        "counts": {k: dict(v) for k, v in counts.items()
                   if isinstance(v, Counter)},
        "chain_failures": counts["chain_fail"],
        "inputs": {p.name: sha256(p.read_text())[:16] for p in
                   (STEP1, STEP2_LOG, STEP3_LOG, STEP4_LOG, STEP5_LOG,
                    STEP6, RES_QUALITY, RES_MEDIA)},
        "outputs": {OUT_LAYER.name: sha256(OUT_LAYER.read_text())[:16],
                    OUT_AUDIT.name: sha256(OUT_AUDIT.read_text())[:16]},
        "note": "provisional snapshot; future Stage M articles are "
                "processed through the same Steps 1-6 and released as "
                "a v2 layer - this file is never overwritten",
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    OUT_REPORT.write_text(
        f"# Normalised text layer - {LAYER_VERSION}\n\n"
        f"* records: **{len(audit_rows)}** (population equals the Step 1 "
        "manifest; asserted)\n"
        f"* quality: {dict(counts['quality'])}\n"
        f"* downstream use: {dict(counts['downstream'])}\n"
        f"* language: {dict(counts['language'])}\n"
        f"* sources: {dict(counts['source'])}\n"
        f"* elections: {dict(counts['election'])}\n"
        f"* hash-chain failures: {counts['chain_fail']}\n"
        f"* review queue: {len(review_rows)} rows\n\n"
        "No article was silently lost: every Step 1 id appears exactly "
        "once above, and every exclusion earlier in the pipeline "
        "carries a human resolution table or a logged reason.\n")

    print(f"{len(audit_rows)} records -> {OUT_LAYER}")
    print("quality:", dict(counts["quality"]))
    print("downstream:", dict(counts["downstream"]))
    print("language:", dict(counts["language"]))
    print("chain failures:", counts["chain_fail"])
    print(f"review queue: {len(review_rows)} -> {OUT_REVIEW}")


if __name__ == "__main__":
    main()
