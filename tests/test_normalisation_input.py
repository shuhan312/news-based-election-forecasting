"""Phase 4 / Step 1 tests: population, source priority, validation,
completeness, provenance/safety, reproducibility.

All fixtures are synthetic records built in tmp_path - no real
corpus files are touched, and a hash check proves it.
"""

import hashlib
import json
from pathlib import Path

import pytest

from src.news_collection.normalisation_input import (
    INPUT_SELECTION_VERSION, enumerate_candidates, select_source,
    validate_selected)


def make_record(tmp: Path, aid="NEWS-test-0001", *, text=None,
                word_count=None, has_full=True, adapter="site_search",
                extract="", html=None, url="https://example.org/a"):
    """One synthetic raw record + optional sidecars under tmp_path."""
    (tmp / "text").mkdir(exist_ok=True)
    (tmp / "html").mkdir(exist_ok=True)
    (tmp / "api").mkdir(exist_ok=True)
    text_path = ""
    if text is not None:
        p = tmp / "text" / f"{aid}.txt"
        p.write_text(text)
        text_path = str(p)
    if html is not None:
        (tmp / "html" / f"{aid}.html").write_text(html)
    wc = word_count if word_count is not None else len((text or "").split())
    return {"article_id": aid,
            "retrieval": {"adapter": adapter, "final_url": url},
            "content": {"has_full_text": has_full and text is not None,
                        "text_path": text_path, "extract": extract,
                        "word_count": wc}}


def run(tmp, rec):
    return select_source(rec, html_dir=tmp / "html", api_raw_dir=tmp / "api")


FULL = ("The by-election campaign continued across the division today. " * 20)

# ------------------------------------------------------------- population
# (population locking itself is exercised end-to-end by the runner on
# real data; here we verify per-record behaviour that supports it)

def test_missing_raw_evidence_is_flagged_not_silent(tmp_path):
    rec = {"article_id": "NEWS-test-0009", "retrieval": {}, "content": {}}
    res = run(tmp_path, rec)
    assert res["text_completeness_status"] == "missing_text"
    assert "no_candidate_sources" in res["validation_flags"]

# --------------------------------------------------------- source priority

def test_full_body_preferred_over_snippet(tmp_path):
    rec = make_record(tmp_path, text=FULL, extract="short teaser")
    res = run(tmp_path, rec)
    assert res["selected_text_source_type"] == "publisher_page"
    assert res["text_completeness_status"] == "full_text"
    assert res["alternative_source_count"] >= 1
    assert any("snippet_only" in a
               for a in res["alternative_source_references"])


def test_archive_full_text_preferred_over_snippet(tmp_path):
    rec = make_record(tmp_path, text=FULL, adapter="wayback",
                      extract="teaser")
    res = run(tmp_path, rec)
    assert res["selected_text_source_type"] == "wayback_capture"
    assert res["selection_priority_rank"] == 3


def test_html_without_extraction_falls_to_review(tmp_path):
    rec = make_record(tmp_path, text=None, html="<html>page</html>")
    res = run(tmp_path, rec)
    assert res["selected_text_source_type"] == "raw_html_only"
    assert res["review_required"] is True
    assert "html_present_but_unextracted" in res["validation_flags"]


def test_selection_is_deterministic(tmp_path):
    rec = make_record(tmp_path, text=FULL, extract="teaser",
                      html="<html>x</html>")
    assert run(tmp_path, rec) == run(tmp_path, rec)

# -------------------------------------------------------- source validation

@pytest.mark.parametrize("bad", [
    "Just a moment... checking your browser",
    "Access denied - error 403",
    "To continue reading, please log in or subscribe",
    "Search results: no results found for your query",
    "Page not found. Error 404.",
])
def test_non_article_pages_demoted_to_review(tmp_path, bad):
    rec = make_record(tmp_path, text=bad + " " + "filler " * 200,
                      word_count=300)
    res = run(tmp_path, rec)
    assert res["review_required"] is True
    assert "non_article_page" in res["validation_flags"]


def test_empty_content_demoted(tmp_path):
    rec = make_record(tmp_path, text="   ", word_count=120)
    res = run(tmp_path, rec)
    assert res["text_completeness_status"] == "review_required"
    assert "empty_content" in res["validation_flags"]


def test_navigation_only_flagged():
    assert "navigation_only" in validate_selected(
        "Home | News | Sport | Menu", original_url="https://x")


def test_missing_url_flagged(tmp_path):
    rec = make_record(tmp_path, text=FULL, url="")
    res = run(tmp_path, rec)
    assert "no_original_url" in res["validation_flags"]
    # traceability doubt is flagged but is not by itself structural
    assert res["text_completeness_status"] == "full_text"

# ------------------------------------------------------ completeness status

def test_partial_text_status(tmp_path):
    rec = make_record(tmp_path, text="Short stub body.", word_count=3)
    res = run(tmp_path, rec)
    assert res["text_completeness_status"] == "partial_text"
    assert res["selection_priority_rank"] == 5


def test_snippet_only_status(tmp_path):
    rec = make_record(tmp_path, text=None,
                      extract="A one-line search snippet about the poll.")
    res = run(tmp_path, rec)
    assert res["selected_text_source_type"] == "snippet_only"
    assert res["text_completeness_status"] == "snippet_only"

# ------------------------------------------------------ provenance / safety

def test_raw_files_unchanged_and_hash_matches(tmp_path):
    rec = make_record(tmp_path, text=FULL)
    p = Path(rec["content"]["text_path"])
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    res = run(tmp_path, rec)
    after = hashlib.sha256(p.read_bytes()).hexdigest()
    assert before == after                      # evidence untouched
    assert res["selected_text_source_hash"] == \
        hashlib.sha256(p.read_text().encode()).hexdigest()


def test_no_rewriting_happens(tmp_path):
    # The selected hash equals the hash of the raw stored text -
    # therefore no cleaning/normalisation occurred in this step.
    odd_text = "Ünïcode &amp; <b>tags</b> stay   exactly as stored. " * 30
    rec = make_record(tmp_path, text=odd_text, word_count=200)
    res = run(tmp_path, rec)
    assert res["selected_text_source_hash"] == \
        hashlib.sha256(odd_text.encode()).hexdigest()


def test_alternatives_retained_for_audit(tmp_path):
    rec = make_record(tmp_path, text=FULL, extract="teaser",
                      html="<html>x</html>")
    res = run(tmp_path, rec)
    refs = " ".join(res["alternative_source_references"])
    assert "raw_html_only" in refs and "snippet_only" in refs


def test_version_stamped(tmp_path):
    res = run(tmp_path, make_record(tmp_path, text=FULL))
    assert res["input_selection_version"] == INPUT_SELECTION_VERSION

# ---------------------------------------------------------- reproducibility

def test_candidate_enumeration_stable_order(tmp_path):
    rec = make_record(tmp_path, text=FULL, extract="teaser",
                      html="<html>x</html>")
    a = enumerate_candidates(rec, html_dir=tmp_path / "html",
                             api_raw_dir=tmp_path / "api")
    b = enumerate_candidates(rec, html_dir=tmp_path / "html",
                             api_raw_dir=tmp_path / "api")
    assert a == b
    assert [c["rank"] for c in a] == sorted(c["rank"] for c in a)
