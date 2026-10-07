"""Deterministic keyword prefilter for V2's outlet-first news collection.

Outlet-first collection returns everything a local outlet published in a
window: sport, crime, weather and listings as well as politics. This filter
runs before any API call and keeps only articles that use political or civic
vocabulary. Survivors go on to the relevance classifier; everything else is
dropped with a recorded reason ("no keyword"), so every discard is explainable
and exactly reproducible.

Place names are deliberately NOT keywords. Almost every local article names a
place, so place names would let nearly everything through and remove the
point of filtering. The price is that a place-only article with no civic
vocabulary is dropped. It also cannot feed V2's party-level features, which
need a party to be mentioned.

The term lists below were fixed as v0 in
v2_design/keyword_prefilter_v1/criteria.md before any recall was measured.
Changes made on dev get a new version name, so results always state which
version produced them.

v1 (amendment A1) changes the input only: the filter reads headline + body.
V1's stored text files hold the body alone, and a party named only in the
headline was being missed. The term lists are unchanged from v0.
"""

from __future__ import annotations

import re

VERSION = "v1"

# --- Party vocabulary -------------------------------------------------------
# Matched case-insensitively, on word boundaries. Generic words that collide
# with ordinary English ("green", "reform", "independent") appear only in
# unambiguous multi-word forms here. The capitalised "Reform" is handled
# separately below.
PARTY_TERMS = [
    "conservative", "conservatives", "tory", "tories",
    "labour",
    "liberal democrat", "liberal democrats", "lib dem", "lib dems",
    "libdem", "libdems",
    "green party", "greens",
    "reform uk", "reform party",
    "ukip",
    # Surrey has strong residents' groups that run for the county council, so
    # they count as parties for relevance purposes.
    "residents association", "residents' association",
    "residents associations", "residents' associations",
    "independent councillor", "independent councillors",
]

# --- Civic and electoral vocabulary ------------------------------------------
# Covers L3/L4-style coverage (council decisions, services, county-wide
# politics), which often never names a party.
CIVIC_TERMS = [
    "council", "councils", "councillor", "councillors", "cllr",
    "election", "elections", "by-election", "by-elections",
    "elected", "polling", "ballot", "ballots",
    "candidate", "candidates",
    "vote", "votes", "voters", "voting",
    "manifesto",
]

# --- Case-sensitive terms ----------------------------------------------------
# Matched as written, because the lower-case forms are ordinary words:
# "MP" vs "mp" (as in "mp3" or "camp"), and "Reform" (the party, usually
# written without "UK" after first mention) vs "reform" (as in "pension
# reform").
CASE_SENSITIVE_TERMS = ["MP", "MPs", "Reform"]


def _compile(terms: list[str], flags: int) -> re.Pattern:
    # One alternation per list, longest terms first, so that "lib dems"
    # matches whole rather than stopping at "lib dem". \b keeps "council"
    # from matching inside "councillor", which has its own entry anyway.
    escaped = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", flags)


_INSENSITIVE = _compile(PARTY_TERMS + CIVIC_TERMS, re.IGNORECASE)
_SENSITIVE = _compile(CASE_SENSITIVE_TERMS, 0)


def article_text(headline: str | None, body: str) -> str:
    """The text the filter reads: headline first, then body (v1).

    Headlines often carry the party name that the body replaces with "the
    government" or "ministers". Collection code must call the filter on this
    combined text, never on the body alone.
    """
    return f"{headline or ''}\n{body}"


def matched_terms(text: str) -> list[str]:
    """Every distinct keyword found in the text, lower-cased except the
    case-sensitive ones, sorted. Kept for audit: it shows why each article
    passed."""
    found = {m.group(0).lower() for m in _INSENSITIVE.finditer(text)}
    found |= {m.group(0) for m in _SENSITIVE.finditer(text)}
    return sorted(found)


def passes(text: str) -> bool:
    """True if the article contains at least one keyword."""
    # search() stops at the first hit, which is faster than collecting every
    # match when only the yes/no decision is needed.
    return bool(_INSENSITIVE.search(text) or _SENSITIVE.search(text))
