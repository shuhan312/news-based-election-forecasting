"""Phase 4 / Step 7 - final audit helpers: deterministic language
check and the quality -> downstream-use mapping (pure logic; the
runner does the IO and the freeze).

Language check
--------------
Deterministic and dependency-free: no ML model, no network, no
randomness - two runs can never disagree. The signal is the fraction
of tokens that are high-frequency English function words, plus the
fraction of alphabetic characters outside ASCII. Codes:

    english            stopword ratio >= EN_RATIO and non-ASCII share
                       below NONLATIN_RATIO.
    non_english        essentially no English function words, or the
                       text is dominated by non-ASCII letters.
    mixed_language     clear English signal AND a heavy non-ASCII
                       share (e.g. long quoted passages in another
                       language).
    insufficient_text  fewer than MIN_TOKENS tokens - too little
                       evidence to say anything.
    uncertain          between the bands -> flagged for review,
                       never guessed.

Confidence is the distance of the stopword ratio from the decision
band, capped to [0,1] - an auditable number, not a probability from a
black box. Language NEVER changes eligibility (E9 upstream already
handled language screening); here it is recorded evidence only.

Downstream-use mapping (deterministic, total)
---------------------------------------------
    valid_full_text     -> ready_full_text
    valid_partial_text  -> ready_partial_text
    snippet_only        -> restricted_snippet_only
    review_required     -> pending_review   (unless a human resolution
                           re-stated the quality status - resolutions
                           are applied BEFORE mapping)
    missing_body        -> not_usable_for_text_analysis
    unusable_text       -> not_usable_for_text_analysis

An uncertain/unexpected language adds a review flag but does not
change the downstream status by itself (specification: language must
not silently alter eligibility or usability).
"""

from __future__ import annotations

import re

RULE_VERSION = "final-audit-v1.0-2026-07-27"
LAYER_VERSION = "normalised_text_layer_v1_provisional"

MIN_TOKENS = 12
EN_RATIO = 0.12          # >= this share of English function words
NONLATIN_RATIO = 0.15    # >= this share of non-ASCII letters

# High-frequency English function words: enough to separate English
# prose from other Latin-script languages, small enough to audit.
EN_STOPWORDS = frozenset(
    "the of and to in a is was for on that with as it at by from be "
    "are this has have had he she they but his her its not or an "
    "will would said which their been".split())

TOKEN = re.compile(r"[A-Za-zÀ-ɏ']+")


def detect_language(text: str) -> dict:
    """Deterministic language evidence for one text."""
    tokens = [t.lower() for t in TOKEN.findall(text or "")]
    letters = [c for c in (text or "") if c.isalpha()]
    non_ascii = sum(1 for c in letters if ord(c) > 127)
    nl_ratio = non_ascii / len(letters) if letters else 0.0

    if len(tokens) < MIN_TOKENS:
        return {"language": "insufficient_text", "confidence": 0.0,
                "stopword_ratio": 0.0, "nonlatin_ratio": round(nl_ratio, 3)}

    sw = sum(1 for t in tokens if t in EN_STOPWORDS)
    ratio = sw / len(tokens)
    base = {"stopword_ratio": round(ratio, 3),
            "nonlatin_ratio": round(nl_ratio, 3)}

    if ratio >= EN_RATIO and nl_ratio < NONLATIN_RATIO:
        conf = min(1.0, 0.5 + (ratio - EN_RATIO) * 4)
        return {"language": "english", "confidence": round(conf, 2), **base}
    if ratio >= EN_RATIO and nl_ratio >= NONLATIN_RATIO:
        return {"language": "mixed_language", "confidence": 0.6, **base}
    if ratio < 0.04:
        return {"language": "non_english",
                "confidence": round(min(1.0, 0.5 + nl_ratio), 2), **base}
    return {"language": "uncertain", "confidence": 0.3, **base}


QUALITY_TO_DOWNSTREAM = {
    "valid_full_text": "ready_full_text",
    "valid_partial_text": "ready_partial_text",
    "snippet_only": "restricted_snippet_only",
    "review_required": "pending_review",
    "missing_body": "not_usable_for_text_analysis",
    "unusable_text": "not_usable_for_text_analysis",
}


def downstream_status(quality_status: str, resolution: str | None) -> str:
    """Map a (possibly human-resolved) quality status to exactly one
    downstream-use status. Resolutions are applied first - a human
    decision recorded in a resolution table replaces the queue status
    it resolved."""
    effective = resolution or quality_status
    return QUALITY_TO_DOWNSTREAM[effective]
