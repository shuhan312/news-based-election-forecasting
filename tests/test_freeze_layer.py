"""Tests for the Phase 6 Step 12 context extraction layer freeze.

Two groups:
  * unit tests of the pure logic (card composition, Z-rules,
    recursive confidence/evidence walkers) on synthetic fixtures;
  * freeze-integrity tests against the actual frozen files on disk
    (skipped cleanly if the gitignored layer file is absent, e.g. on
    a fresh clone) - schema compliance, version metadata, evidence
    re-verification bookkeeping, input-hash drift detection.
"""

import json
from pathlib import Path

import pytest

from src.llm_extraction.freeze_layer import (DATASET_VERSION,
                                             FINAL_SCHEMA_VERSION,
                                             LAYER_FILES,
                                             REQUIRED_CARD_FIELDS,
                                             build_card, check_card,
                                             iter_confidences,
                                             iter_evidence_texts,
                                             sha256_file,
                                             verify_evidence)

META = {"canonical_article_id": "A1", "election_id": "2021",
        "arm": "local", "title": "Council tax rises", "source": "x",
        "author": None, "publication_datetime": "2021-04-01",
        "url": "http://e.x", "mentions_reform": False}


def _layers(**over):
    """A full set of eight valid layer entries, overridable."""
    base = {k: {"record": {"review_status": "auto_validated"},
                "had_errors": False} for k in LAYER_FILES}
    base["pilot_full_schema"]["record"] = {
        "review_status": "auto_validated",
        "issues": {"primary": "should-be-dropped"},
        "entities": [{"name": "P", "entity_type": "party",
                      "evidence_span": {"text": "Council tax rises",
                                        "from_title": True},
                      "confidence": 0.9}]}
    base.update(over)
    return base


def test_card_has_all_required_fields_and_stamps():
    card = build_card("A1", META, _layers(),
                      {"summary": {"review_required": 3},
                       "article_uncertainty_reasons": []},
                      {"day_index": 5})
    assert check_card(card) == []
    for f in REQUIRED_CARD_FIELDS:
        assert f in card
    assert card["schema_version"] == FINAL_SCHEMA_VERSION
    assert card["extraction_version"] == DATASET_VERSION


def test_d1_full_schema_issues_section_excluded():
    card = build_card("A1", META, _layers(), None, None)
    assert "issues" not in card["political_entities"]
    # the focused issues layer still fills the card's issues section
    assert card["issues"] is not None


def test_quarantined_layer_contributes_status_not_data():
    layers = _layers(stance={"record": {"bad": 1}, "had_errors": True})
    card = build_card("A1", META, layers, None, None)
    assert card["stance"] is None
    assert card["validation_status"]["per_layer"]["stance"] \
        == "quarantined"


def test_missing_layer_and_flagged_layer_statuses():
    layers = _layers(framing={"record": {"review_status": "flagged"},
                              "had_errors": False})
    del layers["temporal"]
    card = build_card("A1", META, layers, None, None)
    st = card["validation_status"]["per_layer"]
    assert st["framing"] == "flagged" and st["temporal"] == "missing"
    assert "D6-genre-ambiguity" \
        in card["validation_status"]["class_rulings_applicable"]


def test_deterministic_windows_wrap_temporal_section():
    card = build_card("A1", META, _layers(), None, {"day_index": 5})
    assert card["temporal_horizon"]["deterministic_windows"] \
        == {"day_index": 5}
    assert "llm" in card["temporal_horizon"]


def test_z5_rejects_out_of_range_confidence():
    layers = _layers()
    layers["pilot_full_schema"]["record"]["entities"][0]["confidence"] \
        = 1.7
    card = build_card("A1", META, layers, None, None)
    assert any(e.startswith("Z5") for e in check_card(card))


def test_confidence_walker_finds_nested_scores():
    card = build_card("A1", META, _layers(), None, None)
    assert 0.9 in list(iter_confidences(card))


def test_evidence_walker_and_verifier():
    card = build_card("A1", META, _layers(), None, None)
    spans = list(iter_evidence_texts(card))
    assert ("Council tax rises", True) in spans
    v = verify_evidence(card, body="irrelevant",
                        title="Council tax rises")
    assert v == {"spans": 1, "verified": 1}
    v_bad = verify_evidence(card, body="irrelevant", title="other")
    assert v_bad == {"spans": 1, "verified": 0}


# ---- freeze-integrity tests against the real frozen files ----------

FROZEN = Path("llm_context/llm_context_layer_final.json")
MANIFEST = Path("llm_context/llm_context_version_manifest.json")

needs_frozen = pytest.mark.skipif(
    not (FROZEN.exists() and MANIFEST.exists()),
    reason="frozen layer files not present (gitignored data file)")


@needs_frozen
def test_frozen_layer_every_card_schema_compliant():
    data = json.loads(FROZEN.read_text())
    assert data["article_count"] == len(data["cards"]) == 67
    for card in data["cards"]:
        assert check_card(card) == [], card["article_id"]


@needs_frozen
def test_frozen_layer_confidences_all_in_range():
    data = json.loads(FROZEN.read_text())
    for card in data["cards"]:
        for c in iter_confidences(card):
            assert 0.0 <= c <= 1.0


@needs_frozen
def test_manifest_versions_match_code_constants():
    m = json.loads(MANIFEST.read_text())
    assert m["schema_version"] == FINAL_SCHEMA_VERSION
    assert m["dataset_version"] == DATASET_VERSION
    assert m["model_configuration"]["model"] == "claude-sonnet-5"
    assert set(m["component_contracts"]) == set(LAYER_FILES)


@needs_frozen
def test_manifest_hash_matches_frozen_file():
    """The manifest's recorded hash must equal the actual bytes on
    disk - any tampering with the frozen layer file fails here."""
    m = json.loads(MANIFEST.read_text())
    assert m["frozen_output_sha256"][FROZEN.name] == sha256_file(FROZEN)


@needs_frozen
def test_previous_extraction_layers_unchanged():
    """Input drift detection: every stored layer output the freeze
    consumed must still hash to what the manifest recorded."""
    m = json.loads(MANIFEST.read_text())
    for fname, digest in m["input_file_hashes_sha256"].items():
        p = Path(fname)
        if p.exists():          # gitignored inputs absent on clones
            assert sha256_file(p) == digest, fname


@needs_frozen
def test_frozen_evidence_bookkeeping_complete():
    m = json.loads(MANIFEST.read_text())
    ev = m["evidence_verification"]
    assert ev["verified"] == ev["spans"] > 0
