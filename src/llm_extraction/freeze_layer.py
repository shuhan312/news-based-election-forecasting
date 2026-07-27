"""Phase 6 / Step 12 - context extraction layer freeze (pure logic;
the runner does the IO; NO LLM call anywhere - freezing consolidates
what already exists, it never re-extracts).

Design position, mirroring the Phase 5 mapping-layer freeze:

* A freeze is a CONTRACT, not a copy. The eight stored layer outputs
  stay exactly where they are, byte-untouched; this module composes
  them into one context card per article, stamps every card with the
  final schema/dataset versions, and records the sha256 of every
  input so any later drift is detectable.
* Byte-reproducible: sorted article order, sorted JSON keys where
  order is not semantic, no runtime timestamps (all dates are frozen
  constants). Building twice from the same inputs yields identical
  bytes - that IS the freeze test.
* Overwrite guard: the runner refuses to silently replace a frozen
  file with different bytes. A future change means a new version
  (v2 released alongside), never an edit of v1.

Decisions honoured in the card composition (phase6_research_decisions
_v1.md): D1 - the Step 3 focused layer is the sole issue authority,
so the full-schema record's issues section is NOT copied into the
card (the stored output keeps it; the frozen card contract excludes
it). D6/D7 - genre and absence-value rulings are recorded in the
card's validation_status, not applied as edits.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# ---- frozen version constants --------------------------------------
# The final schema version aggregates the eight per-layer contracts
# that were already frozen individually (each output record carries
# its own layer stamp); "final" marks the set as closed.
FINAL_SCHEMA_VERSION = "llm-context-schema-v1-final-2026-07-27"
FINAL_PROMPT_VERSION = "context-extraction-prompt-v1-final-2026-07-27"
DATASET_VERSION = "context-cards-v1.0-pilot67-2026-07-27"
FREEZE_DATE = "2026-07-27"

# The eight extraction layers in card order. Keys double as the card
# section names (with two renames for readability, see CARD_SECTIONS).
LAYER_FILES = {
    "pilot_full_schema": "llm_context/llm_context_pilot_outputs.json",
    "issues": "llm_context/issue_classification_outputs.json",
    "stance": "llm_context/stance_classification_outputs.json",
    "framing": "llm_context/framing_detection_outputs.json",
    "credit_blame": "llm_context/credit_blame_outputs.json",
    "consequence": "llm_context/electoral_consequence_outputs.json",
    "relevance": "llm_context/local_national_relevance_outputs.json",
    "temporal": "llm_context/temporal_horizon_outputs.json",
}

# layer key -> card section name (spec wording where it differs)
CARD_SECTIONS = {
    "pilot_full_schema": "political_entities",
    "consequence": "expected_electoral_consequence",
    "relevance": "local_national_relevance",
    "temporal": "temporal_horizon",
}

# Every card must carry these top-level fields - the spec's required
# set. confidence + evidence spans live INSIDE each layer section
# (every judgement row carries its own span and confidence) and are
# summarised in confidence_evidence.
REQUIRED_CARD_FIELDS = (
    "article_id", "schema_version", "extraction_version",
    "article_metadata", "political_entities", "issues", "stance",
    "framing", "credit_blame", "expected_electoral_consequence",
    "local_national_relevance", "temporal_horizon",
    "confidence_evidence", "validation_status",
)

# Metadata copied onto the card. publication_datetime is retained in
# the (gitignored) frozen file for provenance; the LLM never saw it -
# the temporal separation is by construction, not by redaction here.
METADATA_FIELDS = (
    "canonical_article_id", "election_id", "arm", "title", "source",
    "author", "publication_datetime", "url", "mentions_reform",
)


def sha256_file(path: Path) -> str:
    """Content hash for the provenance manifest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_card(article_id: str, meta: dict, layers: dict,
               ce_article: dict | None, windows: dict | None) -> dict:
    """Compose one frozen context card.

    layers: layer key -> {"record": ..., "had_errors": bool} for the
    layers that produced a result for this article. Quarantined
    records (validation errors) contribute status only, never data -
    the freeze does not launder them into valid-looking sections.
    """
    card = {"article_id": article_id,
            "schema_version": FINAL_SCHEMA_VERSION,
            "extraction_version": DATASET_VERSION,
            "article_metadata": {f: meta.get(f) for f in METADATA_FIELDS}}

    status = {}
    for layer in LAYER_FILES:
        section = CARD_SECTIONS.get(layer, layer)
        entry = layers.get(layer)
        if entry is None:
            card[section] = None
            status[layer] = "missing"
        elif entry["had_errors"]:
            card[section] = None
            status[layer] = "quarantined"
        else:
            rec = dict(entry["record"])
            if layer == "pilot_full_schema":
                # Decision D1: the focused Step 3 layer is the sole
                # issue authority - the full-schema issues section is
                # excluded from the frozen contract.
                rec.pop("issues", None)
            card[section] = rec
            status[layer] = ("flagged"
                            if rec.get("review_status") == "flagged"
                            else "valid")

    # Deterministic election windows ride with the temporal section -
    # they are code-derived (never LLM output) and marked as such.
    if windows is not None:
        card["temporal_horizon"] = {
            "llm": card["temporal_horizon"],
            "deterministic_windows": windows}

    # Step 10 audit summary: per-article claim counts, confidence
    # distribution and uncertainty narratives (full claim table stays
    # in confidence_evidence_outputs.json, referenced by provenance).
    card["confidence_evidence"] = None if ce_article is None else {
        "summary": ce_article["summary"],
        "article_uncertainty_reasons":
            ce_article["article_uncertainty_reasons"]}

    card["validation_status"] = {
        "per_layer": status,
        "class_rulings_applicable": sorted(
            r for r, hit in (
                ("D6-genre-ambiguity",
                 any(v == "flagged" for v in status.values())),
                ("D7-absence-values", True)) if hit),
        "human_review_pool": (ce_article or {}).get(
            "summary", {}).get("review_required", 0)}
    return card


# ---- freeze validation (rules Z1-Z6, deterministic) -----------------

def check_card(card: dict) -> list[str]:
    """Structural validation of one frozen card. Returns sorted error
    strings; empty list = compliant."""
    errs = []
    for f in REQUIRED_CARD_FIELDS:                          # Z1
        if f not in card:
            errs.append(f"Z1 missing required field {f!r}")
    if card.get("schema_version") != FINAL_SCHEMA_VERSION:  # Z2
        errs.append("Z2 wrong schema_version")
    if card.get("extraction_version") != DATASET_VERSION:
        errs.append("Z2 wrong extraction_version")
    if not card.get("article_id"):                          # Z3
        errs.append("Z3 empty article_id")
    st = (card.get("validation_status") or {}).get("per_layer", {})
    if set(st) != set(LAYER_FILES):                         # Z4
        errs.append("Z4 per-layer status incomplete")
    for c in iter_confidences(card):                        # Z5
        if not isinstance(c, (int, float)) or not 0.0 <= c <= 1.0:
            errs.append(f"Z5 confidence out of range: {c!r}")
    return sorted(errs)


def iter_confidences(obj):
    """Yield every confidence value anywhere in a card (recursive)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("confidence", "confidence_score") and v is not None:
                yield v
            else:
                yield from iter_confidences(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_confidences(item)


def iter_evidence_texts(obj):
    """Yield (text, from_title) for every evidence span in a card -
    used by the runner to re-verify that all evidence links remain
    valid against the article text (rule Z6)."""
    if isinstance(obj, dict):
        span = obj.get("evidence_span")
        if isinstance(span, dict) and span.get("text"):
            yield span["text"], bool(span.get("from_title"))
        for v in obj.values():
            yield from iter_evidence_texts(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_evidence_texts(item)


def verify_evidence(card: dict, body: str, title: str) -> dict:
    """Z6: every span in the frozen card must still match the article
    verbatim (same check the layers passed at extraction time - run
    once more at freeze time so the frozen file self-certifies)."""
    total = ok = 0
    for text, from_title in iter_evidence_texts(card):
        total += 1
        ok += text in (title if from_title else body)
    return {"spans": total, "verified": ok}
