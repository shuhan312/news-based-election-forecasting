"""Attribute an article's issue and framing labels to the parties it names.

## Why this module exists

`build_feature_table` aggregates the stance layer per (election, party,
window) because a stance record names a party in every judgement. The issue
and framing layers carry no party of their own, so both were aggregated per
**election** - and every party in an election therefore received an identical
value. All 144 election-period cells of feature table v2 carry the same
`issue_*_share` and `frame_*_share` for all six parties, while
`party_article_share` in those same cells ranges from 0.011 to 0.614.

That is why both layers failed the reporting gate: `issue_national_politics_
share` has **4** distinct training values within a period against a bar of 10,
but **26** pooled across periods. Sparse within a period and rich across them
is the signature of a per-election aggregation, not of a scarce feature - the
only within-period variation left is between the four elections. It was
recorded as scarcity, and the layers were dropped from every specification on
that reading.

The extraction already holds what is needed to fix it. Every issue record
carries `political_relevance.affected_actors`, populated on 68.1% of records,
and 2,559 of the 2,576 framing records share an article with an issue record,
so a frame can inherit the actor set established for its own article. The
builder simply never read the field. Nothing here re-runs the extraction.

## What counts as naming a party

The base rule is `stance_rescue.PARTY_ALIASES` - the same regex table the
stance layer matched on - so a content feature and a portrayal feature agree
about what "this article is about Labour" means. Inventing a second table here
would let the two disagree silently about the same article, and the arm
reconciliation would not catch it because they live in different columns.

Reusing that table is also accepted where it is narrow: it matches
`reform uk` and `reform party` but not a bare `reform`, and no widening is
done here. A party-identification rule that changes when a new feature needs
it is not a rule.

Actor strings name people as often as parties - `nigel farage` 421 times,
`keir starmer` 413, `theresa may` 185 - so LEADERS extends the base rule to
figures whose affiliation is unambiguous across the whole corpus window. It is
declared separately rather than folded into the aliases because it is a
judgement rather than the repository's definition of a party name, and keeping
it separate lets the attribution rate be measured with and without it.

## The one figure whose party changes

Nigel Farage is named 421 times across six elections and is the only actor in
the corpus whose party moves inside the window, so he is resolved from the
article's own publication date rather than assigned one party or dropped.
Dropping him would cost more attribution than any other single decision here.
"""

from __future__ import annotations

import re
from datetime import date

from src.llm_extraction.stance_rescue import PARTY_ALIASES

# Compiled once at import. The alias table maps a standard party key to a list
# of patterns; an actor string names that party when any pattern matches.
_ALIAS_PATTERNS = {
    party: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for party, patterns in PARTY_ALIASES.items()
}

# Figures whose party affiliation is the same everywhere in the corpus window
# (2013-2026). Restricted to actors that actually appear: adding a name that
# never occurs would suggest a coverage this corpus does not have.
LEADERS = {
    "keir starmer": "labour",
    "jeremy corbyn": "labour",
    "ed miliband": "labour",
    "rachel reeves": "labour",
    "wes streeting": "labour",
    "angela rayner": "labour",
    "theresa may": "conservative",
    "boris johnson": "conservative",
    "david cameron": "conservative",
    "george osborne": "conservative",
    "rishi sunak": "conservative",
    "kemi badenoch": "conservative",
    "ed davey": "liberal_democrat",
    "nick clegg": "liberal_democrat",
}

# Dated transitions behind the Farage mapping, stated as constants so the
# judgement is reviewable rather than buried in a comparison:
#
#   to 2016-11-28   UKIP leader; and through the 2017 county election he
#                   remained UKIP's most identified figure while UKIP itself
#                   contested, so mentions before the Brexit Party existed
#                   attribute to UKIP
#   2019-02-08      Brexit Party registered - NOT one of the six standard
#                   parties, so mentions in that period attribute to nobody
#                   rather than being forced onto a neighbouring party
#   2021-01-06      Brexit Party renamed Reform UK
#
# The 2017 attribution is the debatable one - 65 of the 421 mentions - and the
# build records Farage counts per election so that sensitivity is one filter
# away rather than a re-run.
BREXIT_PARTY_REGISTERED = date(2019, 2, 8)
REFORM_UK_RENAME = date(2021, 1, 6)


def _farage_party(published: date | None) -> str | None:
    # No date means no defensible attribution: the whole point of this branch
    # is that the answer depends on when the article was published.
    if published is None:
        return None
    if published < BREXIT_PARTY_REGISTERED:
        return "ukip"
    if published < REFORM_UK_RENAME:
        return None
    return "reform_uk"


# Actors resolved from the article date rather than from a fixed table.
DATE_DEPENDENT_ACTORS = {"nigel farage": _farage_party}


def publication_date(article: dict) -> date | None:
    """The article's publication date, or None if it is absent or malformed.

    Canonical articles carry `publication_datetime` as an ISO string; only the
    date part is needed and only the date part is trusted.
    """
    raw = str(article.get("publication_datetime") or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def party_for_actor(actor: str, published: date | None = None) -> str | None:
    """The standard party key an actor string names, or None.

    Date-dependent actors are resolved first: their name would not match any
    alias pattern anyway, but resolving them first keeps the precedence
    explicit rather than incidental.
    """
    text = re.sub(r"\s+", " ", str(actor or "").strip())
    if not text:
        return None
    lowered = text.lower()
    if lowered in DATE_DEPENDENT_ACTORS:
        return DATE_DEPENDENT_ACTORS[lowered](published)
    for party, patterns in _ALIAS_PATTERNS.items():
        if any(pattern.search(text) for pattern in patterns):
            return party
    return LEADERS.get(lowered)


def parties_for_actors(actors, published: date | None = None) -> set[str]:
    """The set of standard party keys an `affected_actors` list names.

    A set, because an article naming both "Labour" and "Keir Starmer" is one
    article about Labour, not two. An article naming two different parties
    counts once for each - it genuinely bears on both - which is why the
    per-party counts sum to MORE than the per-election count, and why the
    build reports that multiplier rather than leaving it to be discovered.
    """
    return {party for party in
            (party_for_actor(actor, published) for actor in actors or ())
            if party}
