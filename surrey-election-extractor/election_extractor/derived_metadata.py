"""Load and validate calculated values kept apart from official evidence."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from election_extractor.models import (
    DerivedInput,
    DerivedMetadataRecord,
    DerivedValidationStatus,
    GeographicLevel,
)


# Calculations are deliberately allow-listed rather than supplied as arbitrary
# configuration expressions. A new formula needs code review and tests before
# it can enter the research database.
_FORMULA_SPECS = {
    (
        "derived_rejected_ballots",
        "rejected_ballots",
        "ballot_papers_issued - total_votes",
    ): frozenset({"ballot_papers_issued", "total_votes"}),
    (
        "derived_ballot_papers_issued",
        "ballot_papers_issued",
        "total_votes + rejected_ballots",
    ): frozenset({"total_votes", "rejected_ballots"}),
    (
        "derived_total_votes",
        "total_votes",
        # The rule register additionally requires Seats=1 before this formula
        # can be used: one valid ballot then contributes one candidate vote.
        "ballot_papers_issued - rejected_ballots",
    ): frozenset({"ballot_papers_issued", "rejected_ballots"}),
}


@dataclass(frozen=True)
class DerivedMetadataRule:
    """Describe a reviewed calculation that applies to eligible official pages.

    A rule is not a source of values. It only authorises records whose inputs
    are already present on the same immutable official result page. This keeps
    a compact rule register without hiding per-division inputs or provenance.
    """

    rule_id: str
    election_id: str
    field_name: str
    target_official_field: str
    geographic_level: GeographicLevel
    formula: str
    required_official_values: tuple[DerivedInput, ...]
    retrieval_date: str
    confidence: str
    notes: str | None
    validation_status: DerivedValidationStatus


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


def load_derived_metadata_rules(
    path: str | Path,
    *,
    permitted_election_ids: Iterable[str],
) -> tuple[DerivedMetadataRule, ...]:
    """Load reviewed derivation rules without evaluating any official values.

    The register stays declarative: values, source URLs and input checks are
    supplied only later from the audited official result records.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_rules = payload.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("Derived metadata rules must be a list.")

    permitted = set(permitted_election_ids)
    rules = tuple(_rule_from_mapping(item) for item in raw_rules)
    seen_ids: set[str] = set()
    for rule in rules:
        if rule.election_id not in permitted:
            raise ValueError(
                "Derived metadata rule references an unconfigured election: "
                f"{rule.election_id}."
            )
        if rule.rule_id in seen_ids:
            raise ValueError(f"Duplicate derived metadata rule_id: {rule.rule_id}.")
        seen_ids.add(rule.rule_id)
        _validate_rule_formula(rule)
    return rules


def derive_records_from_rules(
    rules: Iterable[DerivedMetadataRule],
    *,
    official_values_by_division: Mapping[str, Mapping[str, object]],
    official_source_urls_by_division: Mapping[str, str],
) -> tuple[DerivedMetadataRecord, ...]:
    """Create only reproducible calculated records from reviewed rules.

    A page is skipped when an input is absent or when the target field is
    officially published. The function never substitutes a configuration or
    secondary-source value for a missing official input.
    """

    generated: list[DerivedMetadataRecord] = []
    seen_ids: set[str] = set()
    for rule in rules:
        expected_inputs = _formula_inputs(rule.field_name, rule.target_official_field, rule.formula)
        for division_id in sorted(official_values_by_division):
            official_values = official_values_by_division[division_id]
            source_url = official_source_urls_by_division.get(division_id)
            if source_url is None:
                raise ValueError(
                    "Derived metadata rule has no official division source: "
                    f"{division_id}."
                )
            if official_values.get(rule.target_official_field) is not None:
                continue
            if not _required_official_values_match(
                official_values,
                rule.required_official_values,
            ):
                continue
            inputs = _official_inputs(official_values, expected_inputs)
            if inputs is None:
                continue
            value = _calculate(rule.formula, inputs)
            metadata_id = f"{division_id}:{rule.field_name}"
            if metadata_id in seen_ids:
                raise ValueError(f"Duplicate generated derived metadata_id: {metadata_id}.")
            seen_ids.add(metadata_id)
            generated.append(
                DerivedMetadataRecord(
                    metadata_id=metadata_id,
                    election_id=rule.election_id,
                    division_id=division_id,
                    field_name=rule.field_name,
                    target_official_field=rule.target_official_field,
                    value=value,
                    geographic_level=rule.geographic_level,
                    formula=rule.formula,
                    inputs=tuple(
                        DerivedInput(field_name=field_name, value=inputs[field_name])
                        for field_name in sorted(expected_inputs)
                    ),
                    source_url=source_url,
                    evidence_text=(
                        "The official Voting Summary on this result page publishes "
                        + " and ".join(
                            f"{field_name}={inputs[field_name]:,}"
                            for field_name in sorted(expected_inputs)
                        )
                        + (
                            "; required official conditions: "
                            + ", ".join(
                                f"{item.field_name}={item.value}"
                                for item in rule.required_official_values
                            )
                            if rule.required_official_values
                            else ""
                        )
                        + f". Rule {rule.rule_id} calculates {rule.field_name}={value:,}."
                    ),
                    retrieval_date=rule.retrieval_date,
                    confidence=rule.confidence,
                    notes=rule.notes,
                    validation_status=rule.validation_status,
                )
            )
    return tuple(generated)


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

        calculated = _calculate(record.formula, input_values)
        if calculated < 0 or record.value != calculated:
            raise ValueError("Derived metadata result does not reproduce its formula.")


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
    """Allow only reviewed field/formula combinations in this project."""

    expected_inputs = _formula_inputs(
        record.field_name,
        record.target_official_field,
        record.formula,
    )
    if {item.field_name for item in record.inputs} != expected_inputs:
        raise ValueError("Derived metadata inputs do not match its approved formula.")


def _validate_rule_formula(rule: DerivedMetadataRule) -> None:
    """Reject a rule before it can generate records for audited source pages."""

    _formula_inputs(rule.field_name, rule.target_official_field, rule.formula)


def _formula_inputs(
    field_name: str,
    target_official_field: str,
    formula: str,
) -> frozenset[str]:
    """Return the exact inputs for one reviewed formula or reject it."""

    inputs = _FORMULA_SPECS.get((field_name, target_official_field, formula))
    if inputs is None:
        raise ValueError("Derived metadata uses an unsupported formula or field mapping.")
    return inputs


def _official_inputs(
    official_values: Mapping[str, object],
    expected_inputs: frozenset[str],
) -> dict[str, int] | None:
    """Read integer inputs only when the official page published every one."""

    inputs: dict[str, int] = {}
    for field_name in expected_inputs:
        value = official_values.get(field_name)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        inputs[field_name] = value
    return inputs


def _required_official_values_match(
    official_values: Mapping[str, object],
    required_values: tuple[DerivedInput, ...],
) -> bool:
    """Require any semantic preconditions to be published on the same page.

    For example, total candidate votes plus rejected papers identifies issued
    ballot papers only for a page that explicitly publishes one available seat.
    This is a source-level condition, never an assumption about an election year.
    """

    return all(
        official_values.get(condition.field_name) == condition.value
        for condition in required_values
    )


def _calculate(formula: str, inputs: Mapping[str, int]) -> int:
    """Evaluate a reviewed formula without accepting arbitrary expressions."""

    if formula == "ballot_papers_issued - total_votes":
        return inputs["ballot_papers_issued"] - inputs["total_votes"]
    if formula == "total_votes + rejected_ballots":
        return inputs["total_votes"] + inputs["rejected_ballots"]
    if formula == "ballot_papers_issued - rejected_ballots":
        return inputs["ballot_papers_issued"] - inputs["rejected_ballots"]
    raise ValueError(f"Unsupported derived metadata formula: {formula}.")


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


def _rule_from_mapping(item: object) -> DerivedMetadataRule:
    """Validate one rule while keeping its calculation allow-listed in code."""

    if not isinstance(item, Mapping):
        raise ValueError("Each derived metadata rule must be an object.")
    raw_conditions = item.get("required_official_values", [])
    if not isinstance(raw_conditions, list) or not all(
        isinstance(condition, Mapping) for condition in raw_conditions
    ):
        raise ValueError("Derived metadata rule conditions must be a list of objects.")
    try:
        return DerivedMetadataRule(
            rule_id=str(item["rule_id"]),
            election_id=str(item["election_id"]),
            field_name=str(item["field_name"]),
            target_official_field=str(item["target_official_field"]),
            geographic_level=GeographicLevel(str(item["geographic_level"])),
            formula=str(item["formula"]),
            required_official_values=tuple(
                DerivedInput(
                    field_name=str(condition["field_name"]),
                    value=_required_int(condition["value"], "condition value"),
                )
                for condition in raw_conditions
            ),
            retrieval_date=str(item["retrieval_date"]),
            confidence=str(item["confidence"]),
            notes=_optional_text(item.get("notes")),
            validation_status=DerivedValidationStatus(str(item["validation_status"])),
        )
    except KeyError as exc:
        raise ValueError(
            f"Derived metadata rule is missing required field: {exc.args[0]}."
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
