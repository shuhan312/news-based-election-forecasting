"""Phase 4 / Step 2 - conservative HTML and web-template cleaning.

Pure functions only: no file IO, no state. The runner
(build_html_cleaned_articles.py) feeds HTML in and writes results out,
so every rule here is unit-testable against fixtures and two runs on
the same input are byte-identical by construction (nothing here reads
clocks, randomness, or the network).

Design contract (from the Phase 4 Step 2 specification):

* Parse with an established parser (BeautifulSoup / html.parser).
* Remove markup and template furniture; PRESERVE title, standfirst,
  subheadings, paragraphs in original order, quotations, meaningful
  lists, and figure captions.
* Conservative rule: a candidate-for-removal block that might be real
  content (political vocabulary, quotation marks, sentence-like prose)
  is RETAINED and flagged, never silently deleted.
* Challenge/login/search/error pages must not pass as article bodies.
* Raw HTML is never modified - callers read it, never write it.
"""

from __future__ import annotations

import re
from bs4 import BeautifulSoup

# Version stamp recorded on every output row. Bump when ANY rule below
# changes, so two outputs are comparable only when versions match.
RULE_VERSION = "html-clean-v1.0-2026-07-25"

# --- structural removals (never contain article prose) --------------------
STRIP_TAGS = ["script", "style", "noscript", "iframe", "form", "button",
              "svg", "template", "link", "meta"]

# --- template-furniture detection ----------------------------------------
# Matched against a tag's id + class list. Deliberately about WEB
# FURNITURE vocabulary, not topics, mirroring the supervisor's list:
# navigation, adverts, cookie banners, sharing, newsletters,
# subscription/login, related-article modules, footers, search chrome.
FURNITURE_ATTR = re.compile(
    r"(^|[-_ ])(nav|navbar|menu|breadcrumb|advert|ads?|ad-slot|promo"
    r"|sponsor|cookie|consent|gdpr|share|social|newsletter|subscribe"
    r"|signup|sign-in|login|paywall|related|recommend|read-more"
    r"|most-(read|popular)|trending|comments?|footer|copyright|sidebar"
    r"|widget|search|masthead|site-header)($|[-_ ])", re.I)

# Wayback Machine playback chrome injected into every capture; it is
# archive tooling, never article content, so it is removed by id
# prefix without a safety check.
WAYBACK_IDS = ("wm-ipp", "donato", "wm-capinfo")

# --- non-article page detection ------------------------------------------
# If the page-level text looks like a bot-challenge, login wall,
# search-results shell or an error page, the whole document must be
# review_required - a furniture-free extraction of "Access denied"
# would otherwise masquerade as a very short article.
NON_ARTICLE_PAGE = re.compile(
    r"(just a moment|one moment|checking your browser|access denied"
    r"|attention required|verify you are (a )?human|page not found"
    r"|error 40[34]|search results?|no results found"
    r"|to continue reading,? (please )?(log ?in|subscribe|register))", re.I)

# --- safety vetoes (the conservative rule) -------------------------------
# Any hit vetoes furniture-removal of a text-bearing block: political
# speech and quotations are exactly what must never be deleted as
# template noise. A false KEEP costs one stray line; a false REMOVE
# costs evidence.
POLITICAL = re.compile(
    r"(conservative|labour|liberal democrat|lib ?dem|green party|reform"
    r"|ukip|independent|resident|candidate|council(lor)?|election|vote"
    r"|ballot|ward|division|\bmp\b|minister|campaign)", re.I)


def _is_furniture(tag) -> bool:
    """Does this element's id/class vocabulary mark it as template
    furniture? Checks the element itself only - ancestors are handled
    by recursion during traversal."""
    ident = " ".join([tag.get("id") or ""] + (tag.get("class") or []))
    return bool(FURNITURE_ATTR.search(ident))


def _removal_veto(text: str) -> str | None:
    """Return the safety check that forbids removing a furniture-
    flagged block, or None when removal is allowed."""
    t = text.strip()
    if not t:
        return None
    if '"' in t or "“" in t or "‘" in t:
        return "contains_quotation"
    if POLITICAL.search(t):
        return "political_vocabulary"
    if len(t) > 280 and re.search(r"[.!?]\s+\w", t):
        return "multi_sentence_prose"
    return None


# Source-specific article-body selectors, used ONLY when they match;
# every source falls back to the generic strategy below, so an outdated
# selector degrades gracefully instead of failing the article.
SOURCE_SELECTORS = {
    "bbc_surrey": ["main article", "article"],
    "surreylive": ["div.article-body", "article"],
    "surrey_comet": ["div.article-body", "article"],
    "guildford_dragon": ["div.entry-content", "article"],
    "epsom_ewell_times": ["div.entry-content", "article"],
}
GENERIC_SELECTORS = ["article", "main", "body"]

# Content elements harvested, in document order. blockquote covers
# quotations; li covers meaningful lists; figcaption covers captions
# (the protocol keeps captions - they often carry candidate names).
CONTENT_TAGS = ("h1", "h2", "h3", "h4", "p", "blockquote", "li", "figcaption")


def clean_html(html: str, source_id: str = "") -> dict:
    """Clean one raw HTML document. Returns a dict with title, body,
    per-block provenance, metrics and warnings - never raises on
    malformed input (html.parser is tolerant by design).
    """
    soup = BeautifulSoup(html or "", "html.parser")
    warnings: list[str] = []
    flagged_kept: list[str] = []

    # 0. Wayback chrome and structurally content-free tags go first.
    for wid in WAYBACK_IDS:
        for el in soup.select(f'[id^="{wid}"]'):
            el.decompose()
    for tag in soup.find_all(STRIP_TAGS):
        tag.decompose()

    # 1. Title: prefer og:title metadata (set by the publisher), fall
    # back to the first h1, then <title>. Recorded before any body
    # selection so a bad selector cannot lose the headline.
    og = soup.find("meta", attrs={"property": "og:title"})
    h1 = soup.find("h1")
    title = ((og.get("content") if og else "") or
             (h1.get_text(" ", strip=True) if h1 else "") or
             (soup.title.get_text(strip=True) if soup.title else "")).strip()

    visible_before = soup.get_text(" ", strip=True)

    # 2. Non-article page? Judge on title + first slice of visible
    # text BEFORE cleaning, so furniture removal cannot hide the
    # evidence that this was a challenge/login/error shell.
    probe = f"{title} {visible_before[:400]}"
    if NON_ARTICLE_PAGE.search(probe):
        return {"title": title, "body": "", "paragraphs": [],
                "selector_used": "", "status": "review_required",
                "warnings": ["non_article_page"], "flagged_kept": [],
                "input_chars": len(visible_before), "output_chars": 0,
                "removed_ratio": 1.0, "rule_version": RULE_VERSION}

    # 3. Furniture removal with the conservative veto. Elements whose
    # id/class scream "template" are removed outright when their text
    # is clearly not prose; otherwise kept and flagged.
    for el in soup.find_all(_is_furniture):
        text = el.get_text(" ", strip=True)
        veto = _removal_veto(text)
        if veto:
            flagged_kept.append(f"{veto}: {text[:160]}")
        else:
            el.decompose()

    # 4. Body selection: source-specific selectors first, generic
    # fallback second - which one actually fired is recorded per row.
    root, selector_used = None, "generic:none"
    for sel in SOURCE_SELECTORS.get(source_id, []) + GENERIC_SELECTORS:
        found = soup.select_one(sel)
        if found and found.get_text(strip=True):
            root, selector_used = found, (
                f"source:{sel}" if sel in SOURCE_SELECTORS.get(source_id, [])
                else f"generic:{sel}")
            break

    # 5. Harvest content elements in document order; deduplicate
    # nested repeats (a <p> inside an <li> yields text once).
    paragraphs: list[str] = []
    seen_nodes = set()
    if root is not None:
        for el in root.find_all(CONTENT_TAGS):
            if any(id(a) in seen_nodes for a in el.parents):
                continue
            seen_nodes.add(id(el))
            text = el.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
    body = "\n\n".join(paragraphs)

    # 6. Metrics + suspicion flags. removed_ratio compares visible
    # text before vs after; extreme values are warnings, not silent
    # acceptance - the runner escalates them to review_required.
    in_chars, out_chars = len(visible_before), len(body)
    ratio = 1.0 - (out_chars / in_chars) if in_chars else 1.0
    if out_chars == 0:
        warnings.append("empty_extraction")
    elif out_chars < 300:
        warnings.append("very_short_body")
    if ratio > 0.98 and out_chars > 0:
        warnings.append("extreme_removed_ratio")
    if flagged_kept:
        warnings.append("uncertain_blocks_kept")

    status = ("review_required" if "empty_extraction" in warnings
              else "cleaned_with_warnings" if warnings else "cleaned")
    return {"title": title, "body": body, "paragraphs": paragraphs,
            "selector_used": selector_used, "status": status,
            "warnings": warnings, "flagged_kept": flagged_kept,
            "input_chars": in_chars, "output_chars": out_chars,
            "removed_ratio": round(ratio, 4),
            "rule_version": RULE_VERSION}
