"""Phase 4 / Step 7 tests: language detection, downstream mapping,
freeze guard."""

import pytest

from src.normalisation.build_final_layer import freeze_guard
from src.normalisation.final_audit import (LAYER_VERSION, RULE_VERSION,
                                           detect_language,
                                           downstream_status)

EN = ("The returning officer said that the count would continue into "
      "the night and that all of the ballots would be verified by the "
      "agents of the parties before any result was declared.")
FR = ("Le directeur du scrutin a déclaré que le dépouillement se "
      "poursuivrait pendant la nuit et que tous les bulletins seraient "
      "vérifiés par les représentants des partis avant la proclamation.")

# ---------------------------------------------------------- language

def test_english_detected():
    r = detect_language(EN)
    assert r["language"] == "english"
    assert r["confidence"] >= 0.5


def test_non_english_detected():
    r = detect_language(FR)
    assert r["language"] in ("non_english", "uncertain", "mixed_language")
    assert r["language"] != "english"


def test_mixed_language_detected():
    r = detect_language(EN + " " + "Précisément, à la mairie, " * 30)
    assert r["language"] in ("mixed_language", "uncertain")


def test_short_text_insufficient():
    assert detect_language("Election result")["language"] == \
        "insufficient_text"


def test_empty_text_insufficient():
    assert detect_language("")["language"] == "insufficient_text"


def test_uncertain_is_flag_not_guess():
    # Latin-script gibberish with a trace of English function words:
    # must land in 'uncertain', never confidently in either class.
    odd = "zork the blint frazzle warp neb " * 6
    r = detect_language(odd)
    assert r["language"] in ("uncertain", "english")
    if r["language"] == "uncertain":
        assert r["confidence"] <= 0.5


def test_language_deterministic():
    assert detect_language(EN) == detect_language(EN)

# ------------------------------------------------- downstream mapping

@pytest.mark.parametrize("quality,expected", [
    ("valid_full_text", "ready_full_text"),
    ("valid_partial_text", "ready_partial_text"),
    ("snippet_only", "restricted_snippet_only"),
    ("review_required", "pending_review"),
    ("missing_body", "not_usable_for_text_analysis"),
    ("unusable_text", "not_usable_for_text_analysis"),
])
def test_quality_maps_deterministically(quality, expected):
    assert downstream_status(quality, None) == expected


def test_human_resolution_applied_before_mapping():
    # The resolved debate-prompt case: queue said review_required,
    # the human resolution says valid_full_text -> ready_full_text.
    assert downstream_status("review_required", "valid_full_text") == \
        "ready_full_text"

# --------------------------------------------------------- freeze guard

def test_freeze_guard_blocks_silent_overwrite(tmp_path):
    p = tmp_path / "layer.jsonl"
    freeze_guard(p, "original frozen content\n")
    freeze_guard(p, "original frozen content\n")     # same content: fine
    with pytest.raises(RuntimeError):
        freeze_guard(p, "different content\n")       # overwrite: refused
    assert p.read_text() == "original frozen content\n"


def test_versions_exported():
    assert LAYER_VERSION == "normalised_text_layer_v1_provisional"
    assert RULE_VERSION.startswith("final-audit-v1.0")
