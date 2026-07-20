"""Load an explicit, source-preserving party-name lookup for the master database.

The lookup deliberately sits outside extraction.  It can describe a reviewed
standard name and project category, but it never changes the original party
wording published on a Surrey result page.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PARTY_LOOKUP_PATH = (
    Path(__file__).resolve().parents[1] / "config/party_standardisation.json"
)
PARTY_CATEGORIES = frozenset({"established", "emerging", "local", "independent"})
# Surrey result pages use three published labels for UKIP.  They may share one
# analytical name, but Reform UK must remain a separate party as required by
# the supervisor.  Keeping this rule in the loader prevents a later config
# edit from silently merging the two party histories.
UKIP_PUBLISHED_LABELS = frozenset(
    {"UKIP", "UK Independence Party", "UK Independence Party (UKIP)"}
)
UKIP_STANDARD_NAME = "UK Independence Party"
REFORM_STANDARD_NAME = "Reform UK"


class PartyLookupError(ValueError):
    """Raised when a party lookup cannot be used without losing provenance."""


@dataclass(frozen=True)
class PartyLookupEntry:
    """Describe one approved mapping for one exact published party label."""

    original_party_name: str
    standard_party_name: str
    party_category: str | None
    category_basis: str | None
    notes: str | None


def _required_text(entry: object, field_name: str, index: int) -> str:
    """Require non-blank mapping text instead of silently making an alias."""

    if not isinstance(entry, str) or not entry.strip():
        raise PartyLookupError(
            f"Party mapping {index} requires a non-empty {field_name}."
        )
    return entry.strip()


def _optional_text(entry: object, field_name: str, index: int) -> str | None:
    """Keep optional audit notes null rather than converting them to text."""

    if entry is None:
        return None
    if not isinstance(entry, str):
        raise PartyLookupError(f"Party mapping {index} has an invalid {field_name}.")
    return entry.strip() or None


def _entry_from_payload(entry: object, index: int) -> PartyLookupEntry:
    """Validate one reviewed mapping while protecting named party identities."""

    if not isinstance(entry, dict):
        raise PartyLookupError(f"Party mapping {index} must be an object.")
    original = _required_text(entry.get("original_party_name"), "original_party_name", index)
    standard = _required_text(entry.get("standard_party_name"), "standard_party_name", index)
    category = _optional_text(entry.get("party_category"), "party_category", index)
    if category is not None and category not in PARTY_CATEGORIES:
        raise PartyLookupError(
            f"Party mapping {index} has unsupported party_category: {category}."
        )
    # All reviewed UKIP spellings use one analytical identity.  The original
    # source wording is still retained as the dictionary key and in every
    # candidate-result row.
    if original in UKIP_PUBLISHED_LABELS and standard != UKIP_STANDARD_NAME:
        raise PartyLookupError(
            f"Party mapping {index} must map UKIP label {original!r} to "
            f"{UKIP_STANDARD_NAME!r}."
        )
    if original == REFORM_STANDARD_NAME and standard != REFORM_STANDARD_NAME:
        raise PartyLookupError(
            f"Party mapping {index} cannot rename protected party Reform UK."
        )
    return PartyLookupEntry(
        original_party_name=original,
        standard_party_name=standard,
        party_category=category,
        category_basis=_optional_text(entry.get("category_basis"), "category_basis", index),
        notes=_optional_text(entry.get("notes"), "notes", index),
    )


def load_party_lookup(
    path: str | Path = DEFAULT_PARTY_LOOKUP_PATH,
) -> dict[str, PartyLookupEntry]:
    """Load exact-label mappings and reject duplicate or unsafe definitions.

    Entries are keyed by the exact published wording.  An unlisted source label
    is intentionally returned as absent by callers, so no party is standardised
    or categorised by an implicit rule.
    """

    lookup_path = Path(path)
    try:
        payload = json.loads(lookup_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PartyLookupError(f"Party lookup was not found: {lookup_path}") from error
    except json.JSONDecodeError as error:
        raise PartyLookupError(
            f"Party lookup is not valid JSON: {lookup_path}"
        ) from error
    entries = payload.get("party_mappings") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise PartyLookupError("Party lookup requires a party_mappings list.")

    parsed = tuple(
        _entry_from_payload(entry, index) for index, entry in enumerate(entries, start=1)
    )
    names = [entry.original_party_name for entry in parsed]
    if len(names) != len(set(names)):
        raise PartyLookupError("Party lookup contains duplicate original_party_name values.")
    return {entry.original_party_name: entry for entry in parsed}
