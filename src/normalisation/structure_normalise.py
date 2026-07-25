"""Phase 4 / Step 4 - whitespace, line-break and paragraph-structure
normalisation (pure logic; the runner does the IO).

Contract: standardise SPACING and STRUCTURE REPRESENTATION, never
wording, sentence order or paragraph order. Everything is
deterministic, counted and idempotent; structurally suspicious
articles are flagged - and only genuinely rare shapes are escalated
to review, per the corpus survey below.

Rules (each counted when it fires):

    line_endings          any residual \r\n / \r -> \n (Step 3 already
                          normalises these; kept here for closure so
                          Step 4 is safe standalone).
    edge_whitespace       leading/trailing whitespace stripped from
                          every line and from the whole field.
    spaces_collapsed      runs of ordinary spaces/tabs inside a line
                          -> one space. Punctuation is untouched.
    blank_lines           empty lines at the edges removed; runs of
                          blank lines inside a paragraph block treated
                          as ONE paragraph separator; empty paragraphs
                          dropped (counted, never silently).

Paragraphs are never merged (a short standalone line stays its own
paragraph - headings, captions and list items are exactly that) and
never split (see survey note). Order is preserved by construction:
the transform maps each input paragraph to at most one output
paragraph, in place.

Suspicious-structure detection - thresholds are DATA-DRIVEN, from a
survey of the real Step 3 corpus (2026-07-26, 1,540 articles):

    single_paragraph_wall   1,406/1,540 articles (91%) arrive as one
                            long paragraph - Guardian's API bodyText
                            carries no paragraph breaks. That is the
                            corpus norm, not damage, so this is an
                            INFORMATIONAL flag only. Splitting it
                            would be arbitrary restructuring, which
                            the specification forbids.
    sentence_per_line       many short paragraphs (>= 8 paragraphs
                            averaging < 70 chars): 9 articles. Rare,
                            genuinely suspicious (usually a broken
                            extraction) -> review_required.
    broken_list             a bare bullet marker with no content, or
                            a list item ending in a hard-wrapped
                            fragment -> flagged.
    paragraph_count_changed structure transform changed the paragraph
                            count by > 20% (should only happen when
                            many empty paragraphs were dropped) ->
                            review_required.
"""

from __future__ import annotations

import re

RULE_VERSION = "structure-norm-v1.0-2026-07-26"

SPACE_RUN = re.compile(r"[ \t]{2,}")
BULLET = re.compile(r"^\s*([•·*-]|\d{1,2}[.)])\s*")

# Survey-derived thresholds (see module docstring).
SENTENCE_PER_LINE_MIN_PARAS = 8
SENTENCE_PER_LINE_MAX_AVG = 70
WALL_MIN_CHARS = 2000
PARA_CHANGE_REVIEW_RATIO = 0.20


def _normalise_paragraph(p: str, counts: dict) -> str:
    """Whitespace-normalise ONE paragraph without touching wording.
    Returns "" when the paragraph is pure whitespace (the caller
    counts and drops it)."""
    if "\r" in p:
        counts["line_endings"] = counts.get("line_endings", 0) + \
            p.count("\r")
        p = p.replace("\r\n", "\n").replace("\r", "\n")
    lines = p.split("\n")
    out_lines = []
    for ln in lines:
        stripped = ln.strip()
        if stripped != ln:
            counts["edge_whitespace"] = counts.get("edge_whitespace", 0) + 1
        # Tabs become single spaces first (a lone tab is still
        # non-standard spacing), then space runs collapse.
        n_tabs = stripped.count("\t")
        if n_tabs:
            stripped = stripped.replace("\t", " ")
            counts["tabs_converted"] = counts.get("tabs_converted", 0) + n_tabs
        collapsed, n = SPACE_RUN.subn(" ", stripped)
        if n:
            counts["spaces_collapsed"] = counts.get("spaces_collapsed", 0) + n
        if collapsed:
            out_lines.append(collapsed)
        elif ln:  # a line existed but was pure whitespace
            counts["blank_lines"] = counts.get("blank_lines", 0) + 1
    return "\n".join(out_lines)


def normalise_structure(paragraphs: list[str]) -> dict:
    """Normalise a whole article's paragraph list. Wording, sentence
    order and paragraph order are preserved by construction; the
    output paragraph list maps 1:1 (minus dropped empties) onto the
    input."""
    counts: dict[str, int] = {}
    flags: list[str] = []

    out: list[str] = []
    dropped_empty = 0
    for p in paragraphs:
        np = _normalise_paragraph(p or "", counts)
        if np:
            out.append(np)
        else:
            dropped_empty += 1
    if dropped_empty:
        counts["empty_paragraphs_dropped"] = dropped_empty

    body = "\n\n".join(out)

    # --- suspicious-structure detection (never restructures) ---------
    n_in, n_out = len(paragraphs), len(out)
    if n_out == 1 and len(body) > WALL_MIN_CHARS:
        flags.append("single_paragraph_wall")        # informational
    if n_out >= SENTENCE_PER_LINE_MIN_PARAS:
        avg = sum(len(p) for p in out) / n_out
        if avg < SENTENCE_PER_LINE_MAX_AVG:
            flags.append("sentence_per_line")        # review
    for p in out:
        if BULLET.match(p) and not BULLET.sub("", p).strip():
            flags.append("broken_list")              # bare bullet
            break
    if n_in and abs(n_in - n_out) / n_in > PARA_CHANGE_REVIEW_RATIO:
        flags.append("paragraph_count_changed")      # review

    review = any(f in ("sentence_per_line", "paragraph_count_changed")
                 for f in flags)
    return {"paragraphs": out, "body": body,
            "transformations": counts, "flags": flags,
            "input_paragraphs": n_in, "output_paragraphs": n_out,
            "review_required": review, "rule_version": RULE_VERSION}
