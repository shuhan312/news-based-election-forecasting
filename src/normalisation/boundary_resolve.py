"""Phase 4 / Step 5 - title, body and supporting-text boundary
resolution (pure logic; the runner does the IO).

Contract: SEPARATE fields, never rewrite them. Body paragraphs keep
their wording and order; anything lifted out (title repeats, bylines,
captions, publication lines) is moved to its own field, counted, and
only ever removed from the body when the match is DETERMINISTIC.
Ambiguity is flagged, not resolved by guesswork.

Evidence order (specification: metadata before heuristics):

    1. source metadata   - Guardian API sidecar: webTitle (title),
                           fields.byline (author). These are the
                           publisher's own structured fields.
    2. extraction fields - the Step 2 title (og:title / first h1)
                           carried through Steps 3-4.
    3. text markers      - deterministic in-text markers only:
                           "Image caption," prefixes (BBC's fixed
                           caption marker) and "Published <date>"
                           lines (BBC's publication stamp). These are
                           publisher-templated strings, not prose.

Deliberately NOT attempted: inferring subheadings or standfirsts from
unlabelled short paragraphs. Step 2 flattened the tag labels away,
and any length/casing heuristic would misclassify exactly the things
the specification protects (quotes, list items, genuine short opening
paragraphs). Where the evidence does not label a field, the field
stays empty and the paragraphs stay in the body - order intact.

Title-repeat removal: the first body paragraph is removed only when
it is byte-identical to the resolved title (both sides already share
Steps 3-4 normalisation, so equality is well-defined). A prefix or
near match is kept and flagged ``ambiguous_title_repeat``.

Downstream LLM input composition (recorded per row):
    llm_input = title + "\\n\\n" + standfirst + "\\n\\n" + body_text
(empty components skipped; components also stored separately).
"""

from __future__ import annotations

import re

RULE_VERSION = "boundary-v1.0-2026-07-26"
LLM_INPUT_COMPOSITION = "title+standfirst+body_text"

CAPTION_MARKER = re.compile(r"^Image caption,?\s*", re.I)
PUBLISHED_LINE = re.compile(
    r"^Published\s+\d{1,2}\s+\w+(\s+\d{4})?$", re.I)
BYLINE_LINE = re.compile(r"^By\s+[A-Z][\w.'-]+(\s+[A-Z][\w.'-]+){0,4}$")


def resolve_fields(article: dict, api_meta: dict | None = None) -> dict:
    """Resolve one Step 4 article into separated fields.

    ``article``  - the Step 4 JSONL row (title, paragraphs, status).
    ``api_meta`` - the raw API sidecar dict when one exists (Guardian),
                   else None. Read-only; evidence is never modified.
    """
    flags: list[str] = []
    provenance: dict[str, str] = {}

    # ---- title: metadata first, then the extraction title ----------
    extracted_title = (article.get("title") or "").strip()
    api_title = ((api_meta or {}).get("webTitle") or "").strip()
    if api_title:
        title, provenance["title"] = api_title, "api_webTitle"
        if extracted_title and extracted_title != api_title:
            # Two independent sources disagree - keep the publisher's
            # structured field, flag the conflict for audit.
            flags.append("conflicting_titles")
    elif extracted_title:
        title, provenance["title"] = extracted_title, "extraction_og_h1"
    else:
        title, provenance["title"] = "", "none"
        flags.append("missing_title")

    # ---- author: metadata first, then a deterministic byline line --
    api_byline = (((api_meta or {}).get("fields") or {})
                  .get("byline") or "").strip()
    author, provenance["author"] = "", "none"
    if api_byline:
        author, provenance["author"] = api_byline, "api_byline"

    # ---- walk the body: lift deterministic supporting text ---------
    body_paragraphs: list[str] = []
    captions: list[str] = []
    supporting: list[str] = []
    title_repeat_removed = False

    for i, p in enumerate(article.get("paragraphs") or []):
        # exact title repeat at the very start of the body
        if i == 0 and title and p == title:
            title_repeat_removed = True
            continue
        if i == 0 and title and (p.startswith(title) or title.startswith(p)) \
                and p != title:
            flags.append("ambiguous_title_repeat")   # kept in body
        if CAPTION_MARKER.match(p):
            captions.append(CAPTION_MARKER.sub("", p))
            continue
        if PUBLISHED_LINE.match(p):
            supporting.append(p)
            continue
        if not author and BYLINE_LINE.match(p) and i <= 2:
            author, provenance["author"] = p, "body_byline_line"
            continue
        body_paragraphs.append(p)

    if not body_paragraphs:
        flags.append("missing_body")

    body_text = "\n\n".join(body_paragraphs)
    standfirst = ""      # no labelled standfirst evidence survives
    provenance["standfirst"] = "unavailable_upstream"

    llm_input = "\n\n".join(
        part for part in (title, standfirst, body_text) if part)

    review = "missing_body" in flags
    return {
        "title": title, "standfirst": standfirst,
        "body_text": body_text, "body_paragraphs": body_paragraphs,
        "subheadings": [],           # unlabelled upstream - see docstring
        "author_text": author, "caption_text": captions,
        "supporting_text": supporting,
        "field_provenance": provenance,
        "title_repeat_removed": title_repeat_removed,
        "llm_input": llm_input,
        "llm_input_composition": LLM_INPUT_COMPOSITION,
        "warning_flags": flags, "review_required": review,
        "rule_version": RULE_VERSION,
    }
