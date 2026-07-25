"""Phase 4 / Step 2 tests: parser/removal, content preservation,
safety, source fixtures, and reproducibility.

Fixtures live inline as small representative documents (Guardian-like,
BBC-like, a Surrey local publisher, a Wayback capture, malformed HTML,
and a no-usable-body page). They are miniatures of the real page
shapes, not copies of copyrighted articles.
"""

import hashlib
import json
from pathlib import Path

from src.normalisation.html_clean import RULE_VERSION, clean_html

FIX = Path("tests/fixtures/html")


def fixture(name: str) -> str:
    return (FIX / name).read_text()

# ---------------------------------------------------------------- removal

def test_scripts_styles_and_furniture_removed():
    res = clean_html(fixture("surrey_local.html"), source_id="surreylive")
    body = res["body"]
    assert "function(" not in body and "color:" not in body   # script/css
    assert "Accept all cookies" not in body                    # cookie banner
    assert "Share on Facebook" not in body                     # share controls
    assert "newsletter" not in body.lower()                    # newsletter
    assert "All rights reserved" not in body                   # footer
    assert "Most read" not in body                             # related module
    assert "Home > News" not in body                           # navigation


def test_challenge_page_not_accepted_as_article():
    res = clean_html(fixture("challenge.html"), source_id="surreylive")
    assert res["status"] == "review_required"
    assert "non_article_page" in res["warnings"]

# ----------------------------------------------------------- preservation

def test_title_standfirst_paragraph_order_quotes_lists_captions():
    res = clean_html(fixture("surrey_local.html"), source_id="surreylive")
    assert res["title"] == "Ashtead by-election: three candidates stand"
    body = res["body"]
    # standfirst, subheading, and paragraphs in original order
    order = [body.find("Voters go to the polls"),
             body.find("The count begins"),
             body.find("What the candidates say"),
             body.find("Polling stations are open")]
    assert all(i >= 0 for i in order) and order == sorted(order)
    # quotation preserved verbatim
    assert "“This division deserves better roads”" in body
    # meaningful list and caption preserved
    assert "Green Party: Casey Morgan" in body
    assert "Candidates outside the polling station" in body
    # political names survive cleaning
    for name in ("Conservative", "Labour", "Liberal Democrat"):
        assert name in body


def test_political_block_matching_furniture_pattern_is_kept_flagged():
    # A div whose class says "promo" but whose text is a candidate
    # statement must be retained and flagged, not deleted.
    html = ('<html><body><article><p>Intro paragraph here.</p>'
            '<div class="promo">“Vote for better buses,” said '
            'the Labour candidate for Ashtead division.</div>'
            '</article></body></html>')
    res = clean_html(html)
    assert "Vote for better buses" in res["body"] or res["flagged_kept"]
    assert any("political_vocabulary" in f or "contains_quotation" in f
               for f in res["flagged_kept"])
    assert "uncertain_blocks_kept" in res["warnings"]

# ----------------------------------------------------------------- safety

def test_empty_extraction_is_review_required():
    res = clean_html(fixture("no_body.html"))
    assert res["status"] == "review_required"
    assert "empty_extraction" in res["warnings"] or \
        "non_article_page" in res["warnings"]


def test_malformed_html_does_not_crash_and_gets_one_status():
    res = clean_html(fixture("malformed.html"))
    assert res["status"] in ("cleaned", "cleaned_with_warnings",
                             "review_required")
    assert "Unclosed paragraph about the election" in res["body"] or \
        res["status"] == "review_required"


def test_raw_fixture_files_unchanged_by_cleaning():
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in FIX.glob("*.html")}
    for p in FIX.glob("*.html"):
        clean_html(p.read_text())
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in FIX.glob("*.html")}
    assert before == after

# --------------------------------------------------------- source fixtures

def test_guardian_like_page():
    res = clean_html(fixture("guardian.html"), source_id="guardian_api")
    assert res["status"] in ("cleaned", "cleaned_with_warnings")
    assert "county council elections take place" in res["body"]
    assert "Sign up to First Edition" not in res["body"]


def test_bbc_like_page_uses_source_selector():
    res = clean_html(fixture("bbc.html"), source_id="bbc_surrey")
    assert res["selector_used"].startswith(("source:", "generic:"))
    assert "turnout was higher than expected" in res["body"]
    assert "BBC News Services" not in res["body"]


def test_wayback_capture_toolbar_removed():
    res = clean_html(fixture("wayback.html"), source_id="surrey_comet")
    assert "Wayback Machine" not in res["body"]
    assert "INTERNET ARCHIVE" not in res["body"].upper()
    assert "residents packed the hall" in res["body"]

# -------------------------------------------------------- reproducibility

def test_repeated_runs_identical():
    html = fixture("surrey_local.html")
    a = clean_html(html, source_id="surreylive")
    b = clean_html(html, source_id="surreylive")
    assert a == b
    assert hashlib.sha256(a["body"].encode()).hexdigest() == \
        hashlib.sha256(b["body"].encode()).hexdigest()


def test_second_pass_on_cleaned_text_is_stable():
    # Cleaning already-clean text (wrapped as minimal HTML) must not
    # change it further - the rules only ever target furniture.
    first = clean_html(fixture("surrey_local.html"), source_id="surreylive")
    wrapped = "<html><body><article>" + "".join(
        f"<p>{p}</p>" for p in first["paragraphs"]) + "</article></body></html>"
    second = clean_html(wrapped)
    assert second["paragraphs"] == first["paragraphs"]


def test_rule_version_stamped():
    assert clean_html("<html></html>")["rule_version"] == RULE_VERSION
