"""Phase 4 / Step 3 - conservative Unicode, encoding and character
normalisation (pure logic; the runner does the IO).

Contract: fix REPRESENTATION, never wording. After this layer, two
strings that a human would read identically compare equal byte-wise;
nothing a human would read differently is altered. Every transform is
deterministic, counted, and idempotent (normalising twice == once),
and anything uncertain is flagged rather than repaired.

Unicode form: **NFC** (canonical composition). Chosen over NFKC
because compatibility folding would rewrite meaning-bearing forms
(superscripts, fractions, ligatures) - that is wording change, which
this layer must never do. NFC only merges different encodings of the
SAME character (e.g. e + combining-acute -> é).

Transform inventory (applied in this order, each one counted):

    entity_decoded        remaining HTML entities (&amp; &#39; ...) -
                          named and numeric - decoded via html.unescape.
                          Run to a fixed point so double-encoded
                          entities (&amp;amp;) fully resolve.
    mojibake_repaired     ONLY the canonical UTF-8-read-as-Latin-1
                          sequences with a single unambiguous decoding
                          (â€™ -> ', â€œ -> " ...). Anything outside
                          the fixed table is flagged, never guessed.
    unicode_nfc           canonical composition.
    space_normalised      exotic space separators (NBSP, narrow NBSP,
                          en/em/thin spaces - category Zs) -> U+0020.
                          ASCII space, tab and newline are untouched:
                          whitespace COLLAPSING belongs to Step 4.
    crlf_normalised       \r\n and bare \r -> \n (line-ending
                          representation; paragraph boundaries are
                          preserved exactly).
    zero_width_removed    U+200B ZWSP and U+FEFF BOM anywhere; U+200C/
                          U+200D (ZWNJ/ZWJ) only between ASCII
                          letters/spaces, where they cannot be
                          linguistically load-bearing - elsewhere they
                          are KEPT and flagged (emoji sequences and
                          non-Latin scripts legitimately use them).
    control_removed       remaining C0/C1 control characters except
                          \n and \t.

Replacement characters (U+FFFD) mark bytes that were already
destroyed before we ever saw them - there is no deterministic repair,
so they are never touched: counted, flagged, and above a small
threshold the article goes to review_required.
"""

from __future__ import annotations

import html
import re
import unicodedata

RULE_VERSION = "char-norm-v1.0-2026-07-26"

# Canonical mojibake table: UTF-8 bytes of common punctuation misread
# as Latin-1/Windows-1252. Every key has exactly one sane decoding, so
# repair is deterministic; sequences outside this table are evidence
# of damage but NOT deterministically repairable -> flag only.
MOJIBAKE = {
    "â€™": "’", "â€˜": "‘",     # curly single quotes
    "â€œ": "“", "â€\x9d": "”",  # curly double quotes
    "â€“": "–", "â€”": "—",     # en / em dash
    "â€¦": "…",                       # ellipsis
    "Â£": "£", "â‚¬": "€",                 # currency
    "Ã©": "é", "Ã¨": "è", "Ã¡": "á", "Ã ": "à",
    "Ã¶": "ö", "Ã¼": "ü", "Ã±": "ñ", "Ã§": "ç",
}
# Residual patterns that LOOK like mojibake but have no unique repair.
MOJIBAKE_SUSPECT = re.compile(r"[ÃÂâ][-¿€™]")

# Exotic Unicode space separators (category Zs minus U+0020) plus the
# narrow no-break space; all become a plain space.
EXOTIC_SPACES = re.compile(
    "[\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]")

ZERO_WIDTH_ALWAYS = re.compile("[\u200B\uFEFF]")
ZWJ_BETWEEN_ASCII = re.compile(
    "(?<=[A-Za-z0-9 ])[\u200C\u200D](?=[A-Za-z0-9 ])")
ZWJ_ANY = re.compile("[\u200C\u200D]")

# C0/C1 controls minus \n (paragraph structure) and \t (Step 4's job).
CONTROLS = re.compile("[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]")

FFFD_REVIEW_THRESHOLD = 5   # > this many U+FFFD -> review_required


def normalise_text(text: str) -> dict:
    """Normalise one string. Returns the new text plus an exact count
    of every transformation and the flags raised. Pure and idempotent:
    normalise_text(normalise_text(x)['text'])['text'] == that text."""
    counts: dict[str, int] = {}
    flags: list[str] = []
    t = text or ""

    # 1. HTML entities, to a fixed point (max 3 rounds guards against
    # pathological inputs while resolving &amp;amp; style nesting).
    for _ in range(3):
        decoded = html.unescape(t)
        if decoded == t:
            break
        counts["entity_decoded"] = counts.get("entity_decoded", 0) + \
            sum(1 for _ in re.finditer(r"&[#\w]+;", t))
        t = decoded

    # 2. Deterministic mojibake repairs, longest key first so that
    # overlapping sequences resolve identically on every run.
    repaired = 0
    for bad in sorted(MOJIBAKE, key=len, reverse=True):
        n = t.count(bad)
        if n:
            t = t.replace(bad, MOJIBAKE[bad])
            repaired += n
    if repaired:
        counts["mojibake_repaired"] = repaired
    if MOJIBAKE_SUSPECT.search(t):
        flags.append("possible_mojibake_unrepaired")

    # 3. Canonical composition.
    nfc = unicodedata.normalize("NFC", t)
    if nfc != t:
        counts["unicode_nfc"] = sum(1 for a, b in zip(nfc, t) if a != b) or 1
    t = nfc

    # 4. Spacing characters.
    t, n = EXOTIC_SPACES.subn(" ", t)
    if n:
        counts["space_normalised"] = n
    n = t.count("\r")
    if n:
        t = t.replace("\r\n", "\n").replace("\r", "\n")
        counts["crlf_normalised"] = n

    # 5. Zero-width characters.
    t, n1 = ZERO_WIDTH_ALWAYS.subn("", t)
    t, n2 = ZWJ_BETWEEN_ASCII.subn("", t)
    if n1 + n2:
        counts["zero_width_removed"] = n1 + n2
    if ZWJ_ANY.search(t):
        flags.append("zwj_kept_non_ascii_context")

    # 6. Control characters (never \n or \t - see module docstring).
    t, n = CONTROLS.subn("", t)
    if n:
        counts["control_removed"] = n

    # 7. Replacement characters: count and flag, never touch.
    fffd = t.count("\uFFFD")
    if fffd:
        flags.append("replacement_chars_present")
        counts["replacement_chars_found"] = fffd

    review = fffd > FFFD_REVIEW_THRESHOLD
    if review:
        flags.append("encoding_damage_review")
    return {"text": t, "transformations": counts, "flags": flags,
            "review_required": review, "rule_version": RULE_VERSION}
