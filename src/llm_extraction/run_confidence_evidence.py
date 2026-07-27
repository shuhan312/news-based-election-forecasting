"""Phase 6 / Step 10 runner: build the confidence + evidence audit
layer from the SEVEN stored extraction outputs. No LLM call, no API
cost - a deterministic local pass that flattens, re-verifies and
aggregates. Repeated execution over unchanged inputs is
byte-identical.

Usage:
    python3 -m src.llm_extraction.run_confidence_evidence build
"""

import json
import sys
from collections import Counter
from pathlib import Path

from .confidence_evidence import (article_uncertainty_reasons,
                                  check_claim, flatten_record,
                                  summarise)
from .run_pilot import load_articles

CE_VERSION = "confidence-evidence-v1.0-2026-07-27"

# layer name -> (outputs file, record accessor)
LAYERS = {
    "pilot_full_schema":
        Path("llm_context/llm_context_pilot_outputs.json"),
    "issues":
        Path("llm_context/issue_classification_outputs.json"),
    "stance":
        Path("llm_context/stance_classification_outputs.json"),
    "framing":
        Path("llm_context/framing_detection_outputs.json"),
    "credit_blame":
        Path("llm_context/credit_blame_outputs.json"),
    "consequence":
        Path("llm_context/electoral_consequence_outputs.json"),
    "relevance":
        Path("llm_context/local_national_relevance_outputs.json"),
    "temporal":
        Path("llm_context/temporal_horizon_outputs.json"),
}

OUT_JSON = Path("llm_context/confidence_evidence_outputs.json")


def build() -> None:
    arts = load_articles()

    # ---- load every layer's valid records per article ---------------
    per_article: dict[str, dict] = {}
    layer_meta = {}
    for layer, path in LAYERS.items():
        data = json.loads(path.read_text())
        layer_meta[layer] = {"file": path.name,
                             "prompt_version": data.get("prompt_version"),
                             "schema_version": data.get("schema_version")}
        for r in data["results"]:
            rec = r.get("record")
            if rec is None:
                continue
            entry = per_article.setdefault(r["article_id"], {})
            entry[layer] = {"record": rec,
                            "flagged": rec.get("review_status")
                            == "flagged",
                            "had_errors": bool(r["validation_errors"])}

    # ---- flatten, check, aggregate ----------------------------------
    all_claims, articles_out = [], []
    for aid in sorted(per_article):
        a = arts.get(aid, {})
        body, title = a.get("body", ""), a.get("title", "")
        claims = []
        recs_for_reasons = {}
        for layer, entry in per_article[aid].items():
            if entry["had_errors"]:
                continue          # quarantined records stay quarantined
            recs_for_reasons[layer] = entry["record"]
            for claim in flatten_record(layer, entry["record"]):
                claims.append(check_claim(claim, body, title,
                                          entry["flagged"]))
        for c in claims:
            c["article_id"] = aid
        all_claims.extend(claims)
        articles_out.append({
            "article_id": aid,
            "summary": summarise(claims),
            "article_uncertainty_reasons":
                article_uncertainty_reasons(recs_for_reasons),
            "claims": claims})

    corpus = summarise(all_claims)
    flags = Counter(f for c in all_claims
                    for f in c["consistency_flags"])
    OUT_JSON.write_text(json.dumps(
        {"version": CE_VERSION, "layer_provenance": layer_meta,
         "corpus_summary": corpus,
         "consistency_flag_counts": dict(sorted(flags.items())),
         "articles": articles_out}, indent=1,
        ensure_ascii=False) + "\n")

    cov = corpus["supported_claims"] / corpus["total_claims"] * 100
    print(f"{len(articles_out)} articles, "
          f"{corpus['total_claims']} claims -> {OUT_JSON}")
    print(f"evidence coverage: {cov:.1f}% | "
          f"distribution: {corpus['confidence_distribution']}")
    print(f"review required: {corpus['review_required']} | "
          f"flags: {dict(sorted(flags.items()))}")


if __name__ == "__main__":
    {"build": build}[sys.argv[1]]()
