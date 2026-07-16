"""Load and validate calculated values kept apart from official evidence."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from election_extractor.models import (
    DerivedInput,
    DerivedMetadataRecord,
    DerivedValidationStatus,
    GeographicLevel,
)


# Calculations are deliberately allow-listed rather than supplied as arbitrary
# configuration expressions.  A new formula needs code review and tests before
# it can enter the research database.
_APPROVED_FORMULA = "ballot_papers_issued - total_votes"
_APPROVED_FIELD = "derived_rejected_ballots"
_APPROVED_TARGET = "rejected_ballots"
_APPROVED_INPUTS = frozenset({"ballot_papers_issued", "total_votes"})


def load_derived_metadata(
    path: str | Path,
    *,
    permitted_election_ids: Iterable[str],
) -> tuple[DerivedMetadataRecord, ...]:
    """Load a version-controlled calculation register without changing inputs."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("Derived metadata file must contain a records list.")

    permitted = set(permitted_election_ids)
    records = tuple(_record_from_mapping(item) for item in raw_records)
    seen_ids: set[str] = set()
    for record in records:
        if record.election_id not in permitted:
            raise ValueError(
                "Derived metadata references an unconfigured election: "
                f"{record.election_id}."
            )
        if record.metadata_id in seen_ids:
            raise ValueError(f"Duplicate derived metadata_id: {record.metadata_id}.")
        seen_ids.add(record.metadata_id)
    return records


def validate_derived_metadata(
    records: Iterable[DerivedMetadataRecord],
    *,
    official_values_by_division: Mapping[str, Mapping[str, object]],
    official_source_urls_by_division: Mapping[str, str],
) -> None:
    """Verify every calculation against the immutable official source values.

    A calculation is accepted only if the same official result URL contains all
    declared inputs, the target official field is still missing, the approved
    formula exactly reproduces the configured non-negative result, and no
    configuration value is used as a fallback for an absent source value.
    """

    for record in records:
        _validate_supported_formula(record)
        source_url = official_source_urls_by_division.get(record.division_id)
        if source_url is None:
            raise ValueError(
                "Derived metadata has no matching official division source: "
                f"{record.division_id}."
            )
        if record.source_url != source_url:
            raise ValueError(
                "Derived metadata inputs must come from the same official result URL."
            )
        official_values = official_values_by_division.get(record.division_id)
        if official_values is None:
            raise ValueError(
                "Derived metadata has no official values for division: "
                f"{record.division_id}."
            )
        if official_values.get(record.target_official_field) is not None:
            raise ValueError(
                "Derived metadata cannot duplicate an officially published target field."
            )

        input_values = {item.field_name: item.value for item in record.inputs}
        for field_name, configured_value in input_values.items():
            if official_values.get(field_name) != configured_value:
                raise ValueError(
                    "Derived metadata input does not match the official result value: "
                    f"{field_name}."
                )

        calculated = input_values["ballot_papers_issued"] - input_values["total_votes"]
        if calculated < 0 or record.value != calculated:
            raise ValueError(
                "Derived metadata result must equal non-negative issued papers minus total votes."
            )


def records_as_rows(
    records: Iterable[DerivedMetadataRecord],
) -> tuple[dict[str, object], ...]:
    """Return worksheet-ready rows while retaining formula and inputs visibly."""

    return tuple(
        {
            "metadata_id": record.metadata_id,
            "election_id": record.election_id,
            "division_id": record.division_id,
            "field_name": record.field_name,
            "value": record.value,
            "target_official_field": record.target_official_field,
            "formula": record.formula,
            "official_inputs": "; ".join(
                f"{item.field_name}={item.value}" for item in record.inputs
            ),
            "source_url": record.source_url,
            "evidence_text": record.evidence_text,
            "retrieval_date": record.retrieval_date,
            "confidence": record.confidence,
            "notes": record.notes,
            "validation_status": record.validation_status.value,
        }
        for record in sorted(records, key=lambda item: item.metadata_id)
    )


def _validate_supported_formula(record: DerivedMetadataRecord) -> None:
    """Allow only the documented rejected-ballot calculation in this project."""

    if (
        record.field_name != _APPROVED_FIELD
        or record.target_official_field != _APPROVED_TARGET
        or record.formula != _APPROVED_FORMULA
        or {item.field_name for item in record.inputs} != _APPROVED_INPUTS
    ):
        raise ValueError(
            "Derived metadata uses an unsupported formula or field mapping."
        )


def _record_from_mapping(item: object) -> DerivedMetadataRecord:
    """Validate one JSON record before it enters the derived layer."""

    if not isinstance(item, Mapping):
        raise ValueError("Each derived metadata record must be an object.")
    raw_inputs = item.get("inputs")
    if not isinstance(raw_inputs, list):
        raise ValueError("Derived metadata inputs must be a list.")
    if not all(isinstance(input_item, Mapping) for input_item in raw_inputs):
        raise ValueError("Each derived metadata input must be an object.")
    try:
        return DerivedMetadataRecord(
            metadata_id=str(item["metadata_id"]),
            election_id=str(item["election_id"]),
            division_id=str(item["division_id"]),
            field_name=str(item["field_name"]),
            target_official_field=str(item["target_official_field"]),
            value=_required_int(item["value"], "value"),
            geographic_level=GeographicLevel(str(item["geographic_level"])),
            formula=str(item["formula"]),
            inputs=tuple(
                DerivedInput(
                    field_name=str(input_item["field_name"]),
                    value=_required_int(input_item["value"], "input value"),
                )
                for input_item in raw_inputs
            ),
            source_url=str(item["source_url"]),
            evidence_text=str(item["evidence_text"]),
            retrieval_date=str(item["retrieval_date"]),
            confidence=str(item["confidence"]),
            notes=_optional_text(item.get("notes")),
            validation_status=DerivedValidationStatus(str(item["validation_status"])),
        )
    except KeyError as exc:
        raise ValueError(
            f"Derived metadata record is missing required field: {exc.args[0]}."
        ) from exc


def _optional_text(value: object) -> str | None:
    """Preserve an absent optional note as null rather than placeholder text."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_int(value: object, field_name: str) -> int:
    """Accept JSON integer values only; booleans and numeric text are ambiguous."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Derived metadata {field_name} must be an integer.")
    return value
