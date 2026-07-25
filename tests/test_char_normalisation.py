"""Phase 4 / Step 3 tests: entities/Unicode, preservation, encoding
safety, reproducibility."""

import unicodedata

from src.normalisation.char_normalise import (RULE_VERSION,
                                                normalise_text)


def norm(s):
    return normalise_text(s)

# -------------------------------------------------- entity & unicode

def test_named_and_numeric_entities_decoded():
    r = norm("Fish &amp; chips &quot;now&quot; &#39;open&#39;&nbsp;here")
    assert r["text"] == 'Fish & chips "now" \'open\' here'
    assert r["transformations"]["entity_decoded"] >= 4


def test_double_encoded_entities_fully_resolve():
    assert norm("&amp;amp;")["text"] == "&"


def test_decomposed_unicode_composed_to_nfc():
    decomposed = "café"          # e + combining acute
    r = norm(decomposed)
    assert r["text"] == "café"
    assert unicodedata.is_normalized("NFC", r["text"])


def test_nbsp_and_exotic_spaces_become_plain():
    r = norm("10 Downing Street SW1")
    assert r["text"] == "10 Downing Street SW1"


def test_bom_and_zero_width_removed():
    r = norm("﻿Ballot​papers")
    assert r["text"] == "Ballotpapers"
    assert r["transformations"]["zero_width_removed"] == 2


def test_control_characters_removed_but_newlines_kept():
    r = norm("Line one\x00\x0b!\nLine two\x1f.")
    assert r["text"] == "Line one!\nLine two."

# ------------------------------------------------------- preservation

def test_political_names_capitalisation_numbers_quotes_untouched():
    s = ('“Reform UK took 1,234 votes on 2 May 2026,” said the '
         'Liberal Democrat councillor for Ashtead — a 12.5% swing.')
    r = norm(s)
    assert r["text"] == s                     # byte-identical
    assert r["transformations"] == {}


def test_paragraph_boundaries_preserved():
    s = "First paragraph.\n\nSecond paragraph."
    assert norm(s)["text"] == s


def test_valid_non_ascii_preserved():
    s = "Café née Zoë – naïve façade"
    assert norm(s)["text"] == s

# ---------------------------------------------------- encoding safety

def test_deterministic_mojibake_repaired():
    r = norm("councilâ€™s plan â€œworksâ€\x9d â€” done Ã©lite")
    assert r["text"] == "council’s plan “works” — done élite"
    assert r["transformations"]["mojibake_repaired"] == 5


def test_ambiguous_mojibake_flagged_not_guessed():
    s = "odd Ã¤ sequence"       # not in the repair table
    r = norm(s)
    assert "Ã" in r["text"]                    # untouched
    assert "possible_mojibake_unrepaired" in r["flags"]


def test_replacement_chars_flagged_never_touched():
    r = norm("dam�ged")
    assert "�" in r["text"]
    assert "replacement_chars_present" in r["flags"]
    assert r["review_required"] is False       # small count: flag only


def test_heavy_replacement_damage_goes_to_review():
    r = norm("x" + "�" * 10)
    assert r["review_required"] is True
    assert "encoding_damage_review" in r["flags"]

# ---------------------------------------------------- reproducibility

def test_idempotent_and_deterministic():
    s = "Vote &amp; win â€™til 10pm​ today"
    once = norm(s)
    twice = norm(once["text"])
    assert twice["text"] == once["text"]
    assert twice["transformations"] == {}
    assert norm(s) == norm(s)


def test_version_stamped():
    assert norm("x")["rule_version"] == RULE_VERSION
