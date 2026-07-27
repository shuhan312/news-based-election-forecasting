"""Phase 7 / Step 3 runner: build the news scope classification
layer from the frozen context cards + the Step 1 alignment links.

    news_features/news_scope_classification.json

No LLM call, no API cost - the content-based judgement is already
frozen; this pass maps it into the required five-category scheme,
carrying evidence and scores verbatim. Inputs are hash-verified and
read-only; rebuilds are byte-identical.

Usage:
    python3 -m src.news_features.run_scope_classification build
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ..llm_extraction.freeze_layer import sha256_file
from .scope_classification import (SCOPE_VERSION, check_record,
                                   classify_article)

FROZEN = Path("llm_context/llm_context_layer_final.json")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")
ALIGN = Path("news_features/article_entity_alignment.json")
OUT = Path("news_features/news_scope_classification.json")


def build() -> None:
    # freeze integrity before reading anything out of it
    manifest = json.loads(MANIFEST.read_text())
    frozen_hash = sha256_file(FROZEN)
    assert frozen_hash \
        == manifest["frozen_output_sha256"][FROZEN.name], \
        "frozen context layer hash mismatch"

    cards = json.loads(FROZEN.read_text())["cards"]
    align = json.loads(ALIGN.read_text())

    # resolved Step 1 links per article, preserved as join keys
    wards, parties = defaultdict(list), defaultdict(list)
    for r in align["records"]:
        if r["unresolved_flag"]:
            continue
        if r["alignment_type"] == "ward" and r["ward_id"]:
            wards[r["article_id"]].append(r["ward_id"])
        if r["alignment_type"] == "party" and r["party_id"]:
            parties[r["article_id"]].append(r["party_id"])

    records, errors = [], []
    for card in sorted(cards, key=lambda c: c["article_id"]):
        aid = card["article_id"]
        rec = classify_article(card, sorted(set(wards[aid])),
                               sorted(set(parties[aid])))
        errs = check_record(rec)
        if errs:
            errors.append({"article_id": aid, "errors": errs})
        records.append(rec)
    if errors:
        raise SystemExit("scope build aborted: "
                         + json.dumps(errors, indent=1))

    OUT.write_text(json.dumps(
        {"scope_version": SCOPE_VERSION,
         "frozen_layer_sha256": frozen_hash,
         "alignment_version": align["alignment_version"],
         "record_count": len(records),
         "records": records}, indent=1, ensure_ascii=False) + "\n")

    # ---- audit statistics -------------------------------------------
    scopes = Counter(r["scope_classification"] for r in records)
    issues = Counter(r["issue_scope"] for r in records)
    per_source = defaultdict(Counter)
    arm_mismatch = []
    for r in records:
        src = r["article_id"].split("-")[1]
        per_source[src][r["scope_classification"]] += 1
        arm = r["collection_arm_provenance_only"]
        s = r["scope_classification"]
        if s != "uncertain" and (
                (arm == "local" and s == "national_political")
                or (arm == "national" and s in
                    ("ward_specific_local", "surrey_wide_local"))):
            arm_mismatch.append((r["article_id"], arm, s))
    both_scores = [(r["article_id"],
                    r["local_relevance_score"],
                    r["national_relevance_score"])
                   for r in records
                   if r["local_relevance_score"] is not None
                   and r["local_relevance_score"] >= 0.4
                   and r["national_relevance_score"] >= 0.4]
    print(f"{len(records)} records -> {OUT}")
    print("scopes:", dict(scopes.most_common()))
    print("issue_scope:", dict(issues.most_common()))
    print("per-source scope spread:")
    for src, c in sorted(per_source.items()):
        print(f"  {src}: {dict(c)}")
    print(f"arm-vs-content mismatches (D2 provenance): "
          f"{len(arm_mismatch)}", arm_mismatch)
    print(f"dual-relevance articles (both scores >=0.4): "
          f"{len(both_scores)}", both_scores)
    print("uncertain:", [r["article_id"] for r in records
                         if r["scope_classification"] == "uncertain"])
    print("flagged:", [r["article_id"] for r in records
                       if r["review_status"] == "flagged"])


if __name__ == "__main__":
    {"build": build}[sys.argv[1]]()
