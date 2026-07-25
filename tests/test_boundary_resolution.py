"""Phase 4 / Step 5 tests: field separation, boundary safety,
missing/conflict handling, reproducibility."""

from src.normalisation.boundary_resolve import (RULE_VERSION,
                                                resolve_fields)


def art(title="", paragraphs=None, status="normalised"):
    return {"article_id": "NEWS-test-0001", "title": title,
            "paragraphs": paragraphs or [], "status": status,
            "body": "\n\n".join(paragraphs or [])}

# ------------------------------------------------------ field separation

def test_guardian_metadata_preferred_for_title_and_author():
    api = {"webTitle": "Surrey goes to the polls",
           "fields": {"byline": "Jane Reporter"}}
    r = resolve_fields(art(paragraphs=["Body para."]), api)
    assert r["title"] == "Surrey goes to the polls"
    assert r["field_provenance"]["title"] == "api_webTitle"
    assert r["author_text"] == "Jane Reporter"
    assert r["field_provenance"]["author"] == "api_byline"


def test_extraction_title_used_without_api():
    r = resolve_fields(art(title="Local poll result",
                           paragraphs=["Body."]))
    assert r["title"] == "Local poll result"
    assert r["field_provenance"]["title"] == "extraction_og_h1"


def test_caption_marker_lifted_to_captions():
    r = resolve_fields(art(title="T", paragraphs=[
        "First real paragraph.",
        "Image caption, A cordon was put in place",
        "Second real paragraph."]))
    assert r["caption_text"] == ["A cordon was put in place"]
    assert r["body_paragraphs"] == ["First real paragraph.",
                                    "Second real paragraph."]


def test_published_line_lifted_to_supporting():
    r = resolve_fields(art(title="T", paragraphs=[
        "Published 26 April 2021", "Real body."]))
    assert r["supporting_text"] == ["Published 26 April 2021"]
    assert r["body_paragraphs"] == ["Real body."]


def test_body_byline_line_lifted_when_no_api():
    r = resolve_fields(art(title="T", paragraphs=[
        "By Sam Marsden", "The council met on Monday."]))
    assert r["author_text"] == "By Sam Marsden"
    assert r["field_provenance"]["author"] == "body_byline_line"
    assert r["body_paragraphs"] == ["The council met on Monday."]

# ------------------------------------------------------- boundary safety

def test_exact_repeated_title_removed_from_body():
    r = resolve_fields(art(title="Ashtead by-election result",
                           paragraphs=["Ashtead by-election result",
                                       "Counting finished at 2am."]))
    assert r["title_repeat_removed"] is True
    assert r["body_paragraphs"] == ["Counting finished at 2am."]


def test_approximate_title_match_kept_and_flagged():
    r = resolve_fields(art(
        title="Ashtead by-election",
        paragraphs=["Ashtead by-election result declared today.",
                    "More detail follows."]))
    assert r["title_repeat_removed"] is False
    assert "ambiguous_title_repeat" in r["warning_flags"]
    assert len(r["body_paragraphs"]) == 2      # nothing removed


def test_genuine_opening_paragraph_not_removed():
    r = resolve_fields(art(title="Completely different title",
                           paragraphs=["Voters went to the polls."]))
    assert r["body_paragraphs"] == ["Voters went to the polls."]


def test_quotes_lists_short_lines_stay_in_body():
    paras = ["“A quote,” said the Labour candidate.",
             "• Conservative: 1,234", "Short line."]
    r = resolve_fields(art(title="T", paragraphs=paras))
    assert r["body_paragraphs"] == paras
    assert r["subheadings"] == []              # never guessed


def test_order_and_wording_unchanged():
    paras = [f"Paragraph number {i}." for i in range(10)]
    r = resolve_fields(art(title="T", paragraphs=paras))
    assert r["body_paragraphs"] == paras

# --------------------------------------------------- missing and conflict

def test_missing_title_flagged():
    r = resolve_fields(art(paragraphs=["Body only."]))
    assert "missing_title" in r["warning_flags"]
    assert r["review_required"] is False       # body exists


def test_missing_body_review_required():
    r = resolve_fields(art(title="Title only"))
    assert "missing_body" in r["warning_flags"]
    assert r["review_required"] is True


def test_conflicting_titles_flagged_api_wins():
    api = {"webTitle": "API title"}
    r = resolve_fields(art(title="Different extracted title",
                           paragraphs=["Body."]), api)
    assert r["title"] == "API title"
    assert "conflicting_titles" in r["warning_flags"]

# ------------------------------------------------------- reproducibility

def test_deterministic_and_composition_recorded():
    a = art(title="T", paragraphs=["Body one.", "Body two."])
    r1, r2 = resolve_fields(a), resolve_fields(a)
    assert r1 == r2
    assert r1["llm_input_composition"] == "title+standfirst+body_text"
    assert r1["llm_input"] == "T\n\nBody one.\n\nBody two."
    assert r1["rule_version"] == RULE_VERSION
