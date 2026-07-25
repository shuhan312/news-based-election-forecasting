"""Phase 4 / Step 1 - Normalisation input locking and text-source
selection (pure logic; the runner does the IO).

This layer answers exactly three questions for every FINAL eligible
article, and nothing more:

    1. which candidate text representations exist for it,
    2. which one is selected, under one deterministic priority policy,
    3. how complete and how trustworthy that selection is.

It never cleans, rewrites, deduplicates or classifies text, never
re-judges eligibility, and never writes into raw evidence.

Source-priority policy (documented here, enforced in select_source)
--------------------------------------------------------------------
Ranks follow the specification's hierarchy, adapted to this
repository's actual evidence model. At collection time each adapter
already extracted ONE body text per article (content.text_path);
which *kind* of evidence that text came from is recorded by the
adapter name, so fidelity ranking maps onto provenance:

    rank 1  api_full_body    Guardian Content API bodyText - machine-
                             clean full text delivered by the
                             publisher itself; no scraping ambiguity.
    rank 2  publisher_page   full text extracted from the live
                             publisher page our fetcher saved.
    rank 3  wayback_capture  full text extracted from an archived
                             capture (robots-restricted publishers).
    rank 4  raw_html_only    a saved HTML sidecar exists but no
                             extracted text does - the evidence is
                             there, the extraction is not: always
                             review_required, never silently used.
    rank 5  partial_text     an extracted body exists but is below
                             the full-text threshold (stub/truncated).
    rank 6  snippet_only     only the search-API snippet/extract
                             survives; NEVER treated as an article.
    rank 7  none             no usable representation at all.

Within a rank there is nothing left to tie-break: an article has at
most one stored body text and one snippet, so selection is a pure
function of the record - identical inputs always select identically.

Structural validation (validation_flags)
----------------------------------------
The SELECTED text is probed - not cleaned - for shapes that mean
"this is not the article": challenge/login/search/error pages,
navigation-only strings, emptiness, a missing file behind the path,
and a missing original URL (traceability). Any structural failure
demotes the row to review_required; flags are recorded even when
they do not demote, so the audit trail keeps every doubt visible.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

# Bump when any rule in this module changes.
INPUT_SELECTION_VERSION = "input-select-v1.0-2026-07-26"

# Same boundary the eligibility stage used for "full" (its
# text_completeness helper): keeping the two stages numerically
# identical means they can never disagree about what full text is.
FULL_TEXT_MIN_WORDS = 100

# Page-shape probe shared in spirit with html_clean.NON_ARTICLE_PAGE;
# duplicated here deliberately so Step 1 has zero imports from the
# Step 2 layer (the spec forbids Step 1 to depend on cleaning).
NON_ARTICLE = re.compile(
    r"(just a moment|one moment|checking your browser|access denied"
    r"|attention required|verify you are (a )?human|page not found"
    r"|error 40[34]|search results?|no results found"
    r"|to continue reading,? (please )?(log ?in|subscribe|register)"
    r"|enable javascript and cookies)", re.I)

ADAPTER_SOURCE_TYPE = {
    "guardian": ("api_full_body", 1),
    "site_search": ("publisher_page", 2),
    "serper": ("publisher_page", 2),
    "serpapi": ("publisher_page", 2),
    "google_cse": ("publisher_page", 2),
    "manual_import": ("publisher_page", 2),
    "pilot": ("publisher_page", 2),
    "wayback": ("wayback_capture", 3),
}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def enumerate_candidates(record: dict, *, html_dir: Path,
                         api_raw_dir: Path) -> list[dict]:
    """Every text representation that exists for this article, in
    priority order. Pure enumeration: nothing is judged here, so the
    audit record can show what the selector chose BETWEEN."""
    aid = record.get("article_id", "")
    content = record.get("content") or {}
    adapter = (record.get("retrieval") or {}).get("adapter") or ""
    out = []

    text_path = content.get("text_path") or ""
    if text_path and Path(text_path).exists():
        stype, rank = ADAPTER_SOURCE_TYPE.get(adapter, ("publisher_page", 2))
        wc = int(content.get("word_count") or 0)
        full = bool(content.get("has_full_text")) and wc >= FULL_TEXT_MIN_WORDS
        out.append({"type": stype if full else "partial_text",
                    "rank": rank if full else 5,
                    "ref": text_path, "kind": "extracted_text"})
    html_path = html_dir / f"{aid}.html"
    if html_path.exists():
        out.append({"type": "raw_html_only", "rank": 4,
                    "ref": str(html_path), "kind": "raw_html"})
    api_path = api_raw_dir / f"{aid}.json"
    if api_path.exists():
        out.append({"type": "api_raw_reference", "rank": 8,
                    "ref": str(api_path), "kind": "raw_api"})
    if (content.get("extract") or "").strip():
        out.append({"type": "snippet_only", "rank": 6,
                    "ref": "record.content.extract", "kind": "snippet"})
    return sorted(out, key=lambda c: (c["rank"], c["ref"]))


def validate_selected(text: str, *, original_url: str) -> list[str]:
    """Structural probes on the selected text. Returns flag names;
    an empty list means no structural doubt. Probing only - the text
    is never modified."""
    flags = []
    t = (text or "").strip()
    if not t:
        flags.append("empty_content")
        return flags
    if NON_ARTICLE.search(t[:600]):
        flags.append("non_article_page")
    # Navigation-only: short, link-list-like, no sentence punctuation.
    if len(t) < 200 and not re.search(r"[.!?]", t) and \
            re.search(r"(\||>|•|Home|Menu|News)", t, re.I):
        flags.append("navigation_only")
    if not original_url:
        flags.append("no_original_url")
    return flags


def select_source(record: dict, *, html_dir: Path,
                  api_raw_dir: Path) -> dict:
    """Deterministic selection for one article. Returns the full
    per-article result the runner serialises. Raw evidence is only
    ever read."""
    candidates = enumerate_candidates(record, html_dir=html_dir,
                                      api_raw_dir=api_raw_dir)
    # api_raw_reference is provenance, not a text source - it is kept
    # in the alternatives list but never selected as the text.
    selectable = [c for c in candidates if c["type"] != "api_raw_reference"]
    original_url = ((record.get("retrieval") or {}).get("final_url")
                    or (record.get("retrieval") or {}).get("requested_url")
                    or "")

    if not selectable:
        return _result(record, None, candidates, "missing_text",
                       ["no_candidate_sources"], original_url,
                       reason="no text representation exists in any "
                              "evidence store")

    chosen = selectable[0]
    reason = (f"highest-priority available source (rank {chosen['rank']}: "
              f"{chosen['type']}); "
              + (f"{len(selectable) - 1} lower-ranked alternative(s) kept "
                 "for audit" if len(selectable) > 1 else "no alternatives"))

    if chosen["type"] == "raw_html_only":
        # Evidence exists but no validated extraction does: the spec
        # says never silently use or drop it - park it for review.
        return _result(record, chosen, candidates, "review_required",
                       ["html_present_but_unextracted"], original_url,
                       reason=reason)

    if chosen["kind"] == "extracted_text":
        text = Path(chosen["ref"]).read_text(errors="replace")
    else:  # snippet from the record itself
        text = (record.get("content") or {}).get("extract") or ""

    flags = validate_selected(text, original_url=original_url)
    structural_fail = any(f in ("empty_content", "non_article_page")
                          for f in flags)
    if structural_fail:
        status = "review_required"
    elif chosen["type"] == "partial_text":
        status = "partial_text"
    elif chosen["type"] == "snippet_only":
        status = "snippet_only"
    else:
        status = "full_text"
    return _result(record, chosen, candidates, status, flags,
                   original_url, reason=reason, text=text)


def _result(record, chosen, candidates, status, flags, original_url,
            *, reason, text=None) -> dict:
    return {
        "article_id": record.get("article_id", ""),
        "source_name": (record.get("provenance") or {}).get("source_id")
                       or record.get("source_id", ""),
        "original_url": original_url,
        "selected_text_source_type": chosen["type"] if chosen else "none",
        "selected_text_source_path_or_reference":
            chosen["ref"] if chosen else "",
        "selected_text_source_hash": sha256(text) if text else "",
        "text_completeness_status": status,
        "selection_priority_rank": chosen["rank"] if chosen else 7,
        "selection_reason": reason,
        "alternative_source_count": max(len(candidates) - 1, 0),
        "alternative_source_references":
            [f"{c['type']}:{c['ref']}" for c in candidates
             if chosen is None or c is not chosen],
        "validation_flags": flags,
        "review_required": status == "review_required",
        "input_selection_version": INPUT_SELECTION_VERSION,
    }
