"""Load and expose the additive supplementary metadata evidence layer."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from election_extractor.models import (
    ElectionStructureMetadata,
    GeographicLevel,
    SupplementaryMetadataRecord,
    SupplementaryValidationStatus,
)


def load_supplementary_metadata(
    path: str | Path,
    *,
    permitted_election_ids: Iterable[str],
) -> tuple[SupplementaryMetadataRecord, ...]:
    """Load reviewed external evidence without reading official result pages.

    The file is a small, version-controlled evidence register. It is separate
    from extraction audits so each external claim keeps its own URL, passage,
    retrieval date and validation decision.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("Supplementary metadata file must contain a records list.")

    permitted = set(permitted_election_ids)
    records = tuple(_record_from_mapping(item) for item in raw_records)
    seen_ids: set[str] = set()
    for record in records:
        if record.election_id not in permitted:
            raise ValueError(
                "Supplementary metadata references an unconfigured election: "
                f"{record.election_id}."
            )
        if record.metadata_id in seen_ids:
            raise ValueError(f"Duplicate supplementary metadata_id: {record.metadata_id}.")
        seen_ids.add(record.metadata_id)
    return records


def structure_metadata_as_records(
    *,
    election_id: str,
    metadata: Sequence[ElectionStructureMetadata],
    division_ids_by_name: Mapping[str, str],
    retrieval_date: str,
) -> tuple[SupplementaryMetadataRecord, ...]:
    """Expose existing audited Seats evidence through the generic metadata table.

    This is a view over the existing 2021 statutory Seats audit. It does not
    alter the specialised Seats fields or write values into official records.
    """

    records = []
    for item in metadata:
        if item.secondary_number_of_seats is None:
            continue
        division_id = division_ids_by_name.get(item.division_or_ward_name.casefold())
        if division_id is None:
            raise ValueError(
                "Supplementary Seats metadata has no matching official division ID: "
                f"{item.division_or_ward_name}."
            )
        records.append(
            SupplementaryMetadataRecord(
                metadata_id=f"{division_id}:secondary_number_of_seats",
                election_id=election_id,
                division_id=division_id,
                field_name="secondary_number_of_seats",
                value=item.secondary_number_of_seats,
                geographic_level=GeographicLevel.DIVISION,
                source_type=item.seat_source_type or "Secondary statutory evidence",
                source_name=(
                    item.seat_source_name
                    or item.seat_source_type
                    or "Secondary statutory evidence"
                ),
                source_url=item.seat_source_url or "",
                evidence_text=item.seat_evidence_text or "",
                retrieval_date=retrieval_date,
                confidence=item.confidence or "Not recorded",
                notes=item.notes,
                validation_status=SupplementaryValidationStatus.VERIFIED,
            )
        )
    return tuple(records)


def records_as_rows(
    records: Iterable[SupplementaryMetadataRecord],
) -> tuple[dict[str, object], ...]:
    """Return worksheet-ready records while retaining enum values as plain text."""

    return tuple(
        {
            "metadata_id": record.metadata_id,
            "election_id": record.election_id,
            "division_id": record.division_id,
            "field_name": record.field_name,
            "value": record.value,
            "geographic_level": record.geographic_level.value,
            "source_type": record.source_type,
            "source_name": record.source_name,
            "source_url": record.source_url,
            "evidence_text": record.evidence_text,
            "retrieval_date": record.retrieval_date,
            "confidence": record.confidence,
            "notes": record.notes,
            "validation_status": record.validation_status.value,
        }
        for record in sorted(records, key=lambda item: item.metadata_id)
    )


def _record_from_mapping(item: object) -> SupplementaryMetadataRecord:
    """Validate one JSON object before it becomes a usable evidence record."""

    if not isinstance(item, Mapping):
        raise ValueError("Each supplementary metadata record must be an object.")
    try:
        return SupplementaryMetadataRecord(
            metadata_id=str(item["metadata_id"]),
            election_id=str(item["election_id"]),
            division_id=_optional_text(item.get("division_id")),
            field_name=str(item["field_name"]),
            value=item["value"],
            geographic_level=GeographicLevel(str(item["geographic_level"])),
            source_type=str(item["source_type"]),
            source_name=str(item["source_name"]),
            source_url=str(item["source_url"]),
            evidence_text=str(item["evidence_text"]),
            retrieval_date=str(item["retrieval_date"]),
            confidence=str(item["confidence"]),
            notes=_optional_text(item.get("notes")),
            validation_status=SupplementaryValidationStatus(
                str(item["validation_status"])
            ),
        )
    except KeyError as exc:
        raise ValueError(
            f"Supplementary metadata record is missing required field: {exc.args[0]}."
        ) from exc


def _optional_text(value: object) -> str | None:
    """Preserve absent optional values as null instead of placeholder text."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None
