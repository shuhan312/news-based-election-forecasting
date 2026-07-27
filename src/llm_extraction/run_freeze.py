"""Phase 6 / Step 12 runner: freeze the context extraction layer.

Builds, from the eight stored layer outputs + the Step 10 audit +
the deterministic windows (all byte-untouched inputs):

    llm_context/llm_context_layer_final.json        frozen cards
                                                    (gitignored -
                                                    contains verbatim
                                                    quotes)
    llm_context/llm_context_version_manifest.json   versions, model
                                                    config, hashes
    llm_context/context_extraction_prompt_v1_final.md
                                                    all eight system
                                                    prompts verbatim
    llm_context/llm_context_schema_v1_final.json    final aggregated
                                                    schema contract

No LLM call, no API cost. Deterministic: rebuilding from unchanged
inputs is byte-identical, and the overwrite guard refuses to replace
a frozen file with different bytes (release a v2 alongside instead).

Usage:
    python3 -m src.llm_extraction.run_freeze build
"""

import json
import sys
from pathlib import Path

from .credit_blame import build_cb_prompt
from .electoral_consequence import build_ec_prompt
from .framing_detection import build_framing_prompt
from .freeze_layer import (DATASET_VERSION, FINAL_PROMPT_VERSION,
                           FINAL_SCHEMA_VERSION, FREEZE_DATE,
                           LAYER_FILES, build_card, check_card,
                           sha256_file, verify_evidence)
from .issue_classification import build_issue_prompt
from .local_national_relevance import build_ln_prompt
from .pilot_sample import build_system_prompt
from .run_pilot import MODEL, load_articles
from .stance_classification import build_stance_prompt
from .temporal_horizon import build_th_prompt

CE_FILE = Path("llm_context/confidence_evidence_outputs.json")
WINDOWS_FILE = Path("llm_context/temporal_windows_deterministic.json")

OUT_LAYER = Path("llm_context/llm_context_layer_final.json")
OUT_MANIFEST = Path("llm_context/llm_context_version_manifest.json")
OUT_PROMPTS = Path("llm_context/context_extraction_prompt_v1_final.md")
OUT_SCHEMA = Path("llm_context/llm_context_schema_v1_final.json")

# Reproduction record: how every stored output was produced. All
# eight layers used the same frozen model via the Message Batches API
# with prompt caching on the shared system prompt; temperature was
# left at the API default with adaptive thinking enabled, which is
# why MAX_TOKENS differs per layer (thinking shares the budget).
MODEL_CONFIG = {
    "model": MODEL,
    "api": "Anthropic Message Batches API (50% discount)",
    "temperature": "API default (adaptive thinking enabled; "
                   "thinking={'type': 'adaptive'})",
    "system_prompt_caching": "cache_control {'type': 'ephemeral'}",
    "sdk": "anthropic 0.119.0 (Python)",
    "max_tokens_per_layer": {
        "pilot_full_schema": 40000, "issues": 12000, "stance": 16000,
        "framing": 12000, "credit_blame": 20000, "consequence": 16000,
        "relevance": 10000, "temporal": 10000},
    "execution_dates": "2026-07-26 to 2026-07-27",
}

PROMPT_BUILDERS = {
    "pilot_full_schema": build_system_prompt,
    "issues": build_issue_prompt,
    "stance": build_stance_prompt,
    "framing": build_framing_prompt,
    "credit_blame": build_cb_prompt,
    "consequence": build_ec_prompt,
    "relevance": build_ln_prompt,
    "temporal": build_th_prompt,
}


def _write_frozen(path: Path, content: str) -> str:
    """Overwrite guard: identical bytes -> confirm reproduced; new
    file -> write; different bytes -> refuse (freeze discipline)."""
    if path.exists():
        if path.read_text() == content:
            return "reproduced (byte-identical)"
        raise SystemExit(f"REFUSED: {path} exists with different "
                         "bytes - frozen files are never overwritten; "
                         "release a new version alongside instead.")
    path.write_text(content)
    return "written"


def build() -> None:
    arts = load_articles()
    windows = json.loads(WINDOWS_FILE.read_text())
    ce = json.loads(CE_FILE.read_text())
    ce_by_id = {a["article_id"]: a for a in ce["articles"]}

    # ---- load the eight layer outputs (read-only) -------------------
    per_article: dict[str, dict] = {}
    layer_meta = {}
    input_hashes = {}
    for layer, fname in LAYER_FILES.items():
        path = Path(fname)
        data = json.loads(path.read_text())
        input_hashes[fname] = sha256_file(path)
        layer_meta[layer] = {
            "file": path.name,
            "schema_version": data.get("schema_version"),
            "prompt_version": data.get("prompt_version"),
            "rules_version": data.get("rules_version"),
            "batch_ids": [b for b in (data.get("batch_id"),
                                      data.get("retry_batch_id"),
                                      data.get("gap_batch_id")) if b]}
        for r in data["results"]:
            if r.get("record") is None:
                continue
            per_article.setdefault(r["article_id"], {})[layer] = {
                "record": r["record"],
                "had_errors": bool(r["validation_errors"])}
    for f in (CE_FILE, WINDOWS_FILE):
        input_hashes[str(f)] = sha256_file(f)

    # ---- compose + validate every card ------------------------------
    cards, errors, evid = [], [], {"spans": 0, "verified": 0}
    for aid in sorted(per_article):
        meta = arts.get(aid, {})
        card = build_card(aid, meta, per_article[aid],
                          ce_by_id.get(aid), windows.get(aid))
        errs = check_card(card)
        if errs:
            errors.append({"article_id": aid, "errors": errs})
        v = verify_evidence(card, meta.get("body", ""),
                            meta.get("title", ""))
        evid["spans"] += v["spans"]
        evid["verified"] += v["verified"]
        cards.append(card)

    if errors:
        raise SystemExit("freeze aborted - schema violations: "
                         + json.dumps(errors, indent=1))

    layer_status = _write_frozen(OUT_LAYER, json.dumps(
        {"dataset_version": DATASET_VERSION,
         "schema_version": FINAL_SCHEMA_VERSION,
         "freeze_date": FREEZE_DATE,
         "article_count": len(cards),
         "cards": cards}, indent=1, ensure_ascii=False) + "\n")

    # ---- prompt freeze ----------------------------------------------
    prompt_md = [f"# Context extraction prompts - {FINAL_PROMPT_VERSION}",
                 "", "Verbatim system prompts of all eight extraction "
                 "layers, frozen. Each layer's per-article user turn "
                 "contained ONLY the article title and body text plus "
                 "the article_id (never the publication date). Do not "
                 "edit this file - a prompt change is a new version.",
                 ""]
    for layer, builder in PROMPT_BUILDERS.items():
        prompt_md += [f"## Layer: {layer} "
                      f"({layer_meta[layer]['prompt_version']})", "",
                      "```", builder().rstrip(), "```", ""]
    prompt_status = _write_frozen(OUT_PROMPTS, "\n".join(prompt_md))

    # ---- schema freeze ----------------------------------------------
    schema_status = _write_frozen(OUT_SCHEMA, json.dumps(
        {"schema_version": FINAL_SCHEMA_VERSION,
         "freeze_date": FREEZE_DATE,
         "description": "Final aggregated contract of the context "
                        "extraction layer: one card per article, "
                        "composed of the eight per-layer contracts "
                        "below. Field names, types, categories and "
                        "validation rules are those of each layer's "
                        "schema file, unchanged. Any future change "
                        "requires a new schema version released "
                        "alongside, never an edit of this file.",
         "card_required_fields": [
             "article_id", "schema_version", "extraction_version",
             "article_metadata", "political_entities", "issues",
             "stance", "framing", "credit_blame",
             "expected_electoral_consequence",
             "local_national_relevance", "temporal_horizon",
             "confidence_evidence", "validation_status"],
         "component_contracts": layer_meta,
         "taxonomy": "issues-v1.3 (llm_context/issue_taxonomy_v1.3"
                     ".json; decision D1)",
         "issue_authority": "Step 3 focused layer only - the "
                            "full-schema issues section is excluded "
                            "from cards (decision D1)",
         "validation_rules": "per-layer rule series R1-R9, S1-S7, "
                             "T1-T6, F1-F6, C1-C6, E1-E6, G1-G6, "
                             "H1-H6 (in src/llm_extraction/) plus "
                             "freeze rules Z1-Z6 (freeze_layer.py)",
         "decisions_log": "llm_context/phase6_research_decisions_v1"
                          ".md (D1-D7)"},
        indent=1, ensure_ascii=False) + "\n")

    # ---- version manifest -------------------------------------------
    manifest_status = _write_frozen(OUT_MANIFEST, json.dumps(
        {"dataset_version": DATASET_VERSION,
         "schema_version": FINAL_SCHEMA_VERSION,
         "prompt_version": FINAL_PROMPT_VERSION,
         "freeze_date": FREEZE_DATE,
         "model_configuration": MODEL_CONFIG,
         "article_count": len(cards),
         "component_contracts": layer_meta,
         "input_file_hashes_sha256": dict(sorted(input_hashes.items())),
         "frozen_output_sha256": {
             OUT_LAYER.name: sha256_file(OUT_LAYER)},
         "evidence_verification": evid,
         "dependencies": {"python": "3.x", "anthropic": "0.119.0",
                          "runtime_reconstruction":
                          "src/llm_extraction/run_freeze.py build "
                          "(offline, deterministic)"},
         "upstream_provenance": [
             "news_collection/duplicate_mapping_layer_v1_provisional"
             ".csv (Phase 5 freeze)",
             "llm_context/llm_context_pilot_sample_v1.csv "
             "(67-article stratified pilot sample)"]},
        indent=1, ensure_ascii=False) + "\n")

    print(f"cards: {len(cards)} | layer file {layer_status}")
    print(f"prompts {prompt_status} | schema {schema_status} | "
          f"manifest {manifest_status}")
    print(f"evidence spans re-verified: {evid['verified']}/"
          f"{evid['spans']}")


if __name__ == "__main__":
    {"build": build}[sys.argv[1]]()
