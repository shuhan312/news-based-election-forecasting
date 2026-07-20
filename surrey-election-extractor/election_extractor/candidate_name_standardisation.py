"""Create a display-standard candidate name without asserting identity.

Official result pages use more than one presentation convention. In
particular, many 2013 rows use ``Surname, Given names`` while later pages often
use ``Given names Surname``. This module makes that explicit punctuation-based
formatting consistent for analysis while the original published value remains
unchanged in the master database.

The function deliberately does not use fuzzy matching, initials, party,
location or another election to decide that two names describe one person.
Person continuity remains governed by the separate official-evidence layer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class StandardCandidateName:
    """One deterministic display value and the rule that produced it."""

    value: str
    status: str


def standardise_candidate_name(published_name: str) -> StandardCandidateName:
    """Return a conservative display standardisation of one published name.

    Whitespace and Unicode representation are normalised in the analytical
    copy. A name is reordered only when one comma clearly separates a nonempty
    surname from nonempty given names. Names without that exact structure keep
    their published token order because inferring a surname would be unsafe.
    """

    if not isinstance(published_name, str) or not published_name.strip():
        raise ValueError("Published candidate name must be non-empty text.")

    normalised = _normalise_spacing(published_name)
    if normalised.count(",") != 1:
        return StandardCandidateName(
            value=normalised,
            status="published_order_retained",
        )

    surname, given_names = (part.strip() for part in normalised.split(",", 1))
    if not surname or not given_names:
        # A comma alone is not enough evidence to infer the intended order.
        return StandardCandidateName(
            value=normalised,
            status="published_order_retained_ambiguous_comma",
        )

    return StandardCandidateName(
        value=f"{given_names} {_display_case_surname(surname)}",
        status="surname_comma_order_reformatted",
    )


def _normalise_spacing(value: str) -> str:
    """Normalise the analytical copy while preserving the source field."""

    unicode_value = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", unicode_value).strip()


def _display_case_surname(value: str) -> str:
    """Reduce a fully uppercase surname to display case, preserving mixed case."""

    # ``str.title`` handles apostrophes and hyphens for the explicit all-caps
    # cases in the audited data. Mixed-case forms such as ``D'Avray`` are kept
    # exactly as published rather than being guessed at.
    return value.title() if value.isupper() else value
