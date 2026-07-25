"""Phase 4 / Step 4 tests: whitespace, structure preservation,
safety, reproducibility."""

from src.normalisation.structure_normalise import (RULE_VERSION,
                                                   normalise_structure)


def norm(paras):
    return normalise_structure(paras)

# ------------------------------------------------------------ whitespace

def test_repeated_spaces_and_tabs_collapsed():
    r = norm(["The  count\tbegan   at 10pm."])
    assert r["body"] == "The count began at 10pm."
    assert r["transformations"]["spaces_collapsed"] >= 1


def test_leading_trailing_whitespace_stripped():
    r = norm(["   Polls open at 7am.   "])
    assert r["body"] == "Polls open at 7am."


def test_mixed_line_endings_normalised():
    r = norm(["Line one.\r\nLine two.\rLine three."])
    assert r["body"] == "Line one.\nLine two.\nLine three."
    assert r["transformations"]["line_endings"] == 2


def test_blank_edges_and_empty_paragraphs_dropped_counted():
    r = norm(["", "  ", "Real paragraph.", ""])
    assert r["paragraphs"] == ["Real paragraph."]
    assert r["transformations"]["empty_paragraphs_dropped"] == 3


def test_internal_blank_lines_become_one_separator():
    r = norm(["First.\n\n\n\nStill first paragraph text."])
    assert r["body"] == "First.\nStill first paragraph text."

# -------------------------------------------------- structure preservation

def test_paragraph_and_sentence_order_preserved():
    paras = ["Heading", "First sentence. Second sentence.",
             "“A quotation stays put,” said the Labour candidate.",
             "• Conservative: 1,234 votes", "• Reform UK: 987 votes",
             "Final paragraph."]
    r = norm(paras)
    assert r["paragraphs"] == paras            # byte-identical
    assert r["transformations"] == {}


def test_short_standalone_paragraphs_not_merged():
    r = norm(["Photo caption.", "Another short line."])
    assert r["output_paragraphs"] == 2


def test_numbers_punctuation_names_untouched():
    s = "Turnout: 34.7% — 12,456 ballots; Lib Dem hold (maj. 401)."
    assert norm([s])["body"] == s

# ------------------------------------------------------------------ safety

def test_wall_flagged_informational_not_review():
    # 91% of the real corpus is a single long paragraph (Guardian API
    # bodyText) - flagged for visibility, never sent to review.
    r = norm(["Long sentence. " * 200])
    assert "single_paragraph_wall" in r["flags"]
    assert r["review_required"] is False


def test_sentence_per_line_goes_to_review():
    r = norm([f"Short sentence number {i}." for i in range(12)])
    assert "sentence_per_line" in r["flags"]
    assert r["review_required"] is True


def test_bare_bullet_flags_broken_list():
    r = norm(["• Real item", "•"])
    assert "broken_list" in r["flags"]


def test_large_paragraph_count_change_goes_to_review():
    r = norm(["Real."] + [""] * 5)      # 5/6 paragraphs vanish
    assert "paragraph_count_changed" in r["flags"]
    assert r["review_required"] is True


def test_no_arbitrary_split_or_merge():
    paras = ["One paragraph with several sentences. More here.",
             "Second paragraph."]
    r = norm(paras)
    assert r["output_paragraphs"] == r["input_paragraphs"] == 2

# ---------------------------------------------------------- reproducibility

def test_idempotent_and_deterministic():
    paras = ["  Spaced   text \r\n here. ", "", "• item   one"]
    once = norm(paras)
    twice = norm(once["paragraphs"])
    assert twice["paragraphs"] == once["paragraphs"]
    assert twice["transformations"] == {}
    assert norm(paras) == norm(paras)


def test_version_stamped():
    assert norm(["x"])["rule_version"] == RULE_VERSION
