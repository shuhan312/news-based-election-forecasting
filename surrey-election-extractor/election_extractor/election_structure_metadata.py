"""Load separately audited election-structure metadata for workbook export."""

import json
from collections.abc import Mapping
from pathlib import Path

from election_extractor.models import ElectionStructureMetadata


def load_secondary_seats_audit(
    audit_path: str | Path,
    *,
    election_year: int | None,
    election_name: str | None,
    authority: str | None,
) -> tuple[ElectionStructureMetadata, ...]:
    """Convert a completed secondary Seats audit into additive metadata records.

    The audit is an explicit input rather than an automatic fallback.  This
    prevents auxiliary evidence from silently changing official extraction
    records, validation outcomes, or area statuses.
    """
    audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    records = audit.get("records")
    if not isinstance(records, list):
        raise ValueError("Secondary Seats audit must contain a records list.")

    metadata_records = []
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("Each secondary Seats audit record must be an object.")

        # Values are mapped field-for-field.  In particular, no secondary
        # value is copied into official_number_of_seats when that field is null.
        secondary_value = (
            record.get("secondary_seats_value")
            if record.get("secondary_seats_available") is True
            else None
        )
        metadata_records.append(
            ElectionStructureMetadata(
                election_year=election_year,
                election_name=election_name,
                authority=authority,
                division_or_ward_name=str(record["division_name"]),
                official_number_of_seats=record.get("official_number_of_seats"),
                secondary_number_of_seats=secondary_value,
                seat_source_type=record.get("source_type"),
                seat_source_url=record.get("source_url"),
                seat_evidence_text=record.get("evidence_text"),
                confidence=record.get("confidence"),
                notes=record.get("notes"),
            )
        )
    return tuple(metadata_records)
