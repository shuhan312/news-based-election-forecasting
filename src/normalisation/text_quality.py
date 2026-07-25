"""Phase 4 / Step 6 - text quality validation and missing-body status
resolution (pure logic; the runner does the IO).

Contract: JUDGE usability, never change content. Every Step 5 article
gets exactly one controlled status with a written reason and the full
evidence trail (signals + flags); nothing is deleted, nothing is
fetched, nothing is invented.

Status vocabulary (exactly one per article):

    valid_full_text     usable body, no disqualifying signal.
    valid_partial_text  usable but demonstrably incomplete text
                        (upstream partial-source selection, or a
                        truncation signal on a short body).
    snippet_only        only a search snippet ever existed (upstream
                        Step 1 status; never promoted to body text).
    missing_body        no body text exists. Includes the six
                        human-resolved media-only articles (video /
                        cartoon): their resolution table is honoured,
                        so they carry review_required=False.
    review_required     conflicting or suspicious evidence a human
                        must arbitrate.
    unusable_text       the "body" is demonstrably not article prose
                        (challenge/error/login shell, or boilerplate-
                        dominated) - kept on file, excluded downstream.

Multi-signal design (specification item 3) - no single word count
decides anything. Signals, each recorded per article:

    counts        body/title/summary words and characters, paragraphs.
    upstream      Step 1 completeness status (full/partial/snippet/
                  missing), Step 3 encoding flags, Step 4 structure
                  flags, and the two human resolution tables.
    shape         title-only bodies (body shorter than twice the
                  title), near-empty bodies (< NEAR_EMPTY_WORDS),
                  genuine-short bodies (SHORT_MIN..FULL_MIN words -
                  VALID, flagged short_article, per specification
                  item 4).
    damage        non-article shells (same probe family as Steps 1-2),
                  boilerplate density (furniture-matching paragraphs /
                  total), duplicate paragraphs, truncation (body ends
                  without terminal punctuation or with an ellipsis).
    consistency   upstream said full_text but the body is near-empty
                  now, or vice versa -> conflicting evidence -> review.

Threshold rationale: FULL_MIN_WORDS=80 sits below Step 1's 100-word
"full" line so that a body that lost a few words to lifted captions
or bylines in Step 5 does not flap between statuses; SHORT_MIN_WORDS
=25 is the floor under which prose cannot carry even a one-sentence
news brief plus attribution.
"""

from __future__ import annotations

import re

RULE_VERSION = "text-quality-v1.0-2026-07-27"

FULL_MIN_WORDS = 80
SHORT_MIN_WORDS = 25
NEAR_EMPTY_WORDS = 25
BOILERPLATE_DOMINANCE = 0.30
DUPLICATE_RATIO_REVIEW = 0.30

# Same probe family as Steps 1-2: page shells that mean "this is not
# an article", checked against the START of the body.
NON_ARTICLE = re.compile(
    r"(just a moment|one moment|checking your browser|access denied"
    r"|attention required|verify you are (a )?human|page not found"
    r"|error 40[34]|no results found"
    r"|to continue reading,? (please )?(log ?in|subscribe|register)"
    r"|enable javascript and cookies)", re.I)

# Light furniture probe for density measurement (per paragraph).
FURNITURE = re.compile(
    r"(cookie|sign up|subscribe|newsletter|share (this|on)|read more"
    r"|related (articles?|stories)|all rights reserved|follow us)", re.I)

TERMINAL_PUNCT = tuple('.!?"\'”’…)')


def words(s: str) -> int:
    return len((s or "").split())


def assess_quality(article: dict, upstream: dict) -> dict:
    """Assess one Step 5 article.

    ``article``  - the Step 5 JSONL row (title, body_text,
                   body_paragraphs, warning_flags, status).
    ``upstream`` - collected earlier-step evidence for this id:
                   step1_status, step3_flags, step4_flags,
                   media_resolution (bool), structure_resolution
                   (bool). Read-only.
    """
    flags: list[str] = []
    signals: dict[str, object] = {}

    title = article.get("title") or ""
    body = article.get("body_text") or ""
    paragraphs = article.get("body_paragraphs") or []
    standfirst = article.get("standfirst") or ""

    signals["body_words"] = bw = words(body)
    signals["body_chars"] = len(body)
    signals["title_words"] = tw = words(title)
    signals["summary_words"] = words(standfirst)
    signals["paragraphs"] = len(paragraphs)
    step1 = upstream.get("step1_status", "")
    signals["step1_status"] = step1

    # Inherited warnings become part of this layer's evidence trail.
    for f in (upstream.get("step3_flags") or []):
        if f:
            flags.append(f"step3:{f}")
    for f in (upstream.get("step4_flags") or []):
        if f and f != "carried_from_step3":
            flags.append(f"step4:{f}")

    # ---- terminal statuses decided by presence, not length ----------
    if not body.strip():
        if upstream.get("media_resolution"):
            return _result("missing_body",
                           "media-only article (video/cartoon) per the "
                           "human resolution table; no body text has "
                           "ever existed",
                           flags + ["media_only_resolved"], signals,
                           review=False)
        if step1 == "snippet_only":
            return _result("snippet_only",
                           "only a search snippet was ever stored",
                           flags, signals, review=False)
        return _result("missing_body", "no body text present",
                       flags + ["empty_body"], signals, review=True)

    # ---- non-article shells: unusable regardless of length ----------
    if NON_ARTICLE.search(body[:400]):
        return _result("unusable_text",
                       "body opens with challenge/error/login shell "
                       "text, not article prose",
                       flags + ["non_article_shell"], signals,
                       review=False)

    # ---- damage and shape signals -----------------------------------
    furniture = sum(1 for p in paragraphs if FURNITURE.search(p))
    density = furniture / len(paragraphs) if paragraphs else 0.0
    signals["boilerplate_density"] = round(density, 3)
    if density > BOILERPLATE_DOMINANCE and len(paragraphs) >= 3:
        flags.append("boilerplate_dominated")

    longish = [p for p in paragraphs if len(p) > 30]
    dups = len(longish) - len(set(longish))
    signals["duplicate_paragraphs"] = dups
    if dups:
        flags.append("duplicate_paragraphs")

    truncated = not body.rstrip().endswith(TERMINAL_PUNCT) \
        or body.rstrip().endswith(("...", "…"))
    if truncated:
        flags.append("possible_truncation")

    # Title-only shape: the body is no longer than an echo of
    # the title. A tiny body with a tiny title is NOT this case -
    # it falls through to the near-empty review path instead.
    if tw >= 4 and bw <= 2 * tw:
        flags.append("title_only_shape")

    # ---- consistency with upstream completeness ---------------------
    if step1 == "full_text" and bw < NEAR_EMPTY_WORDS:
        flags.append("conflicting_completeness_evidence")

    # ---- decide -----------------------------------------------------
    if "boilerplate_dominated" in flags:
        return _result("unusable_text",
                       f"furniture-matching paragraphs dominate "
                       f"({density:.0%} of {len(paragraphs)})",
                       flags, signals, review=False)
    if "conflicting_completeness_evidence" in flags or \
            "title_only_shape" in flags:
        return _result("review_required",
                       "completeness evidence conflicts (upstream vs "
                       "current body size / title-only shape)",
                       flags, signals, review=True)
    if dups and len(longish) and dups / len(longish) > DUPLICATE_RATIO_REVIEW:
        return _result("review_required",
                       "large share of duplicated paragraphs",
                       flags, signals, review=True)
    if step1 == "partial_text":
        return _result("valid_partial_text",
                       "upstream source was a partial text",
                       flags, signals, review=False)
    if bw < NEAR_EMPTY_WORDS:
        return _result("review_required",
                       "near-empty body needs a human decision",
                       flags + ["near_empty_body"], signals, review=True)
    if bw < FULL_MIN_WORDS:
        if truncated:
            return _result("valid_partial_text",
                           "short body with a truncation signal",
                           flags, signals, review=False)
        return _result("valid_full_text",
                       "genuinely short article (complete prose, "
                       "terminal punctuation)",
                       flags + ["short_article"], signals, review=False)
    return _result("valid_full_text", "usable full body",
                   flags, signals, review=False)


def _result(status, reason, flags, signals, *, review) -> dict:
    return {"quality_status": status, "status_reason": reason,
            "warning_flags": sorted(set(flags)), "signals": signals,
            "review_required": review, "rule_version": RULE_VERSION}
