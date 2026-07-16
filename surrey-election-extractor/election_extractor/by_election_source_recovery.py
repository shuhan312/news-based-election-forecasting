"""Load the read-only official-source recovery audit for missing by-elections.

The audit distinguishes a complete official declaration from a Council-minute
winner confirmation. A winner-only document cannot supply a complete candidate
contest, so this module never creates or alters candidate result records.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from election_extractor.by_election_results import (
    DEFAULT_CATALOGUE_PATH,
    ByElectionEvent,
    load_by_election_catalogue,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_RECOVERY_PATH = PROJECT_ROOT / "config/by_election_source_recovery_audit.json"
RECOVERY_STATUSES = {
    "official_winner_confirmation_only",
    "official_declaration_integrated",
    "official_result_page_integrated",
    "official_archive_event_only",
}
INTEGRATED_RECOVERY_STATUSES = {
    "official_declaration_integrated",
    "official_result_page_integrated",
}


@dataclass(frozen=True)
class ByElectionSourceRecovery:
    """Describe the evidence available for one previously unresolved event."""

    election_id: str
    result_evidence_status: str
    source_type: str
    source_url: str
    evidence_text: str
    candidate_results_integrated: bool
    missing_official_information: tuple[str, ...]
    notes: str


def _text(value: object, field_name: str) -> str:
    """Require an explicit audit value rather than silently applying a default."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"By-election source recovery requires non-empty {field_name}.")
    return value.strip()


def _official_url(value: object) -> str:
    """Accept only public HTTP(S) URLs and never store credentials in the audit."""

    url = _text(value, "source_url")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("By-election source recovery requires a public source_url.")
    return url


def load_by_election_source_recovery_audit(
    path: str | Path = DEFAULT_SOURCE_RECOVERY_PATH,
    *,
    catalogue: Sequence[ByElectionEvent] | None = None,
) -> tuple[ByElectionSourceRecovery, ...]:
    """Load recovery evidence and reject entries outside the existing catalogue."""

    events = catalogue if catalogue is not None else load_by_election_catalogue()
    event_ids = {event.election_id for event in events}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, Mapping) else None
    if not isinstance(records, list):
        raise ValueError("By-election source recovery audit requires a records list.")

    parsed = []
    for raw in records:
        if not isinstance(raw, Mapping):
            raise ValueError("Each source recovery record must be an object.")
        election_id = _text(raw.get("election_id"), "election_id")
        if election_id not in event_ids:
            raise ValueError("Source recovery record is not an existing by-election event.")
        status = _text(raw.get("result_evidence_status"), "result_evidence_status")
        if status not in RECOVERY_STATUSES:
            raise ValueError(f"Unsupported by-election source recovery status: {status}.")
        integrated = raw.get("candidate_results_integrated")
        if not isinstance(integrated, bool):
            raise ValueError("candidate_results_integrated must be true or false.")
        # Only a published official result source with candidate rows can
        # justify integration. This does not claim every possible field exists.
        if integrated != (status in INTEGRATED_RECOVERY_STATUSES):
            raise ValueError("Recovery status and integration decision conflict.")
        missing = raw.get("missing_official_information")
        # A complete official result page may publish every field requested by
        # this audit, so an empty list is a meaningful, permitted value.
        if not isinstance(missing, list) or not all(isinstance(item, str) and item for item in missing):
            raise ValueError("missing_official_information must be a text list.")
        parsed.append(
            ByElectionSourceRecovery(
                election_id=election_id,
                result_evidence_status=status,
                source_type=_text(raw.get("source_type"), "source_type"),
                source_url=_official_url(raw.get("source_url")),
                evidence_text=_text(raw.get("evidence_text"), "evidence_text"),
                candidate_results_integrated=integrated,
                missing_official_information=tuple(missing),
                notes=_text(raw.get("notes"), "notes"),
            )
        )
    identifiers = [record.election_id for record in parsed]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("By-election source recovery audit contains duplicate election IDs.")
    return tuple(sorted(parsed, key=lambda record: record.election_id))


def unresolved_source_recovery_ids(
    audit: Sequence[ByElectionSourceRecovery] | None = None,
) -> tuple[str, ...]:
    """Return only events that still lack a complete official candidate result."""

    records = audit if audit is not None else load_by_election_source_recovery_audit()
    return tuple(
        record.election_id
        for record in records
        if not record.candidate_results_integrated
    )
