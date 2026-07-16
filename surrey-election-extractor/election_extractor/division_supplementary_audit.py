"""Audit named 2013 division evidence without repairing official extraction data."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from election_extractor.extraction import CandidateResultRecord
from election_extractor.models import (
    GeographicLevel,
    SupplementaryMetadataRecord,
    SupplementaryValidationStatus,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = PROJECT_ROOT / "config/2013_division_turnout_evidence.json"


@dataclass(frozen=True)
class DivisionEvidenceAudit:
    """Keep the report and approved metadata records as separate outputs."""

    report: dict[str, object]
    supplementary_records: tuple[SupplementaryMetadataRecord, ...]


def audit_2013_division_evidence(
    records: Sequence[CandidateResultRecord],
    evidence_path: str | Path = EVIDENCE_PATH,
) -> DivisionEvidenceAudit:
    """Match only explicitly reviewed Council evidence to official divisions.

    The evidence register uses the official published division name as its key
    and retains the Council announcement heading separately. No fuzzy matching,
    county-wide propagation, calculation or replacement of official values is
    performed by this audit.
    """

    payload = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    divisions = _division_index(records)
    accepted = _accepted_evidence(payload, divisions)
    unresolved = _unresolved_evidence(payload, divisions)
    _validate_coverage(divisions, accepted, unresolved)

    source = _mapping(payload.get("source"), "source")
    turnout_records = tuple(
        _turnout_metadata_record(
            division_name=division_name,
            division_id=division_id,
            value=value,
            source_division_name=source_division_name,
            source=source,
        )
        for division_name, division_id, value, source_division_name in accepted
    )
    ballot_issued = _accepted_ballot_papers_issued(payload, divisions, records)
    ballot_issued_records = tuple(
        _ballot_papers_issued_metadata_record(
            division_name=division_name,
            division_id=division_id,
            value=value,
            source_division_name=source_division_name,
            source=ballot_source,
        )
        for (
            division_name,
            division_id,
            value,
            source_division_name,
            ballot_source,
        ) in ballot_issued
    )
    division_rows = []
    accepted_by_name = {item[0]: item for item in accepted}
    unresolved_by_name = {item[0]: item for item in unresolved}
    ballot_issued_by_name = {item[0]: item for item in ballot_issued}
    for division_name, division_id in sorted(divisions.items()):
        turnout = accepted_by_name.get(division_name)
        unresolved_turnout = unresolved_by_name.get(division_name)
        division_rows.append(
            {
                "division_name": division_name,
                "division_id": division_id,
                "official_turnout": None,
                "supplementary_turnout_available": turnout is not None,
                "supplementary_turnout_value": turnout[2] if turnout else None,
                "turnout_source_division_name": turnout[3] if turnout else (
                    unresolved_turnout[1] if unresolved_turnout else None
                ),
                "turnout_source_url": source["source_url"] if turnout else (
                    unresolved_turnout[2] if unresolved_turnout else None
                ),
                "turnout_status": "accepted" if turnout else "unresolved",
                "turnout_reason": (
                    "Named official Council result section states the turnout value."
                    if turnout
                    else unresolved_turnout[3]
                ),
                "official_ballot_papers_issued": None,
                "supplementary_ballot_papers_issued_available": division_name
                in ballot_issued_by_name,
                "supplementary_ballot_papers_issued": (
                    ballot_issued_by_name[division_name][2]
                    if division_name in ballot_issued_by_name
                    else None
                ),
                "ballot_papers_issued_status": (
                    "accepted" if division_name in ballot_issued_by_name else "unresolved"
                ),
                "ballot_papers_issued_reason": (
                    "Named official Woking declaration publishes this value and its "
                    "electorate agrees with the official Surrey result page."
                    if division_name in ballot_issued_by_name
                    else _ballot_reason(payload)
                ),
            }
        )

    report = {
        "audit_title": "2013 Surrey County Council Division Supplementary Evidence Audit",
        "scope": (
            "Read-only review of the 81 official 2013 divisions. Only named, "
            "explicit Council values with verified division scope become supplementary metadata."
        ),
        "data_principle": (
            "Supplementary values remain separate from official division fields "
            "and do not change layered completeness."
        ),
        "sources": [source],
        "summary": {
            "official_divisions_audited": len(divisions),
            "accepted_supplementary_division_turnout": len(turnout_records),
            "unresolved_division_turnout": len(divisions) - len(turnout_records),
            "accepted_supplementary_ballot_papers_issued": len(ballot_issued_records),
            "unresolved_ballot_papers_issued": len(divisions) - len(ballot_issued_records),
        },
        "records": division_rows,
        "integration_rule": (
            "Only the accepted turnout and ballot-papers-issued records may enter the "
            "Supplementary Metadata table. Official turnout and ballot_papers_issued remain NULL."
        ),
    }
    return DivisionEvidenceAudit(
        report=report,
        supplementary_records=turnout_records + ballot_issued_records,
    )


def audit_markdown(report: Mapping[str, object]) -> str:
    """Render a concise reviewer-facing account of accepted and unresolved values."""

    summary = _mapping(report.get("summary"), "summary")
    lines = [
        "# 2013 Surrey Division Supplementary Evidence Audit",
        "",
        "## Outcome",
        "",
        f"- Official divisions audited: {summary['official_divisions_audited']}",
        f"- Accepted supplementary division turnout records: {summary['accepted_supplementary_division_turnout']}",
        f"- Unresolved division turnout records: {summary['unresolved_division_turnout']}",
        f"- Accepted supplementary ballot-papers-issued records: {summary['accepted_supplementary_ballot_papers_issued']}",
        f"- Unresolved ballot-papers-issued records: {summary['unresolved_ballot_papers_issued']}",
        "",
        "## Source boundary",
        "",
        "- The Surrey Council announcement is treated as supplementary division evidence, not as a replacement for the official individual result pages.",
        "- Every accepted turnout record has a named Council result section and a stated value.",
        "- Foxhills, Thorpe & Virginia Water remains unresolved because its Council result section labels turnout but gives no number.",
        "- Only named ballot-papers-issued values whose official Woking declaration electorate agrees with the Surrey result page are accepted.",
        "- The Byfleets remains unresolved: the Woking declaration states an electorate of 10,016 whereas the Surrey result page states 10,019.",
        "- Official `turnout` and `ballot_papers_issued` values remain NULL, and division completeness is unchanged.",
        "",
    ]
    return "\n".join(lines)


def _division_index(records: Sequence[CandidateResultRecord]) -> dict[str, str]:
    """Build one official division ID per published division name."""

    by_name: defaultdict[str, set[str]] = defaultdict(set)
    for record in records:
        if record.division_ward_name is None:
            raise ValueError("2013 audit cannot proceed without a published division name.")
        by_name[record.division_ward_name].add(_division_id(record.source_url))
    index = {}
    for division_name, identifiers in by_name.items():
        if len(identifiers) != 1:
            raise ValueError(
                f"Division {division_name} has conflicting official result identifiers."
            )
        index[division_name] = next(iter(identifiers))
    return index


def _accepted_evidence(
    payload: Mapping[str, object],
    divisions: Mapping[str, str],
) -> tuple[tuple[str, str, float, str], ...]:
    """Validate manually reviewed evidence without normalising names automatically."""

    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("Division turnout evidence must contain a records list.")
    accepted = []
    seen_names: set[str] = set()
    for item in raw_records:
        record = _mapping(item, "turnout evidence record")
        division_name = _required_text(record, "division_name")
        if division_name not in divisions:
            raise ValueError(
                "Turnout evidence does not use an exact official division name: "
                f"{division_name}."
            )
        if division_name in seen_names:
            raise ValueError(f"Duplicate turnout evidence for {division_name}.")
        value = record.get("value")
        if not isinstance(value, (int, float)):
            raise ValueError(f"Turnout value must be numeric for {division_name}.")
        if not 0 <= float(value) <= 100:
            raise ValueError(f"Turnout value is outside 0-100 for {division_name}.")
        seen_names.add(division_name)
        accepted.append(
            (
                division_name,
                divisions[division_name],
                float(value),
                _required_text(record, "source_division_name"),
            )
        )
    return tuple(accepted)


def _unresolved_evidence(
    payload: Mapping[str, object],
    divisions: Mapping[str, str],
) -> tuple[tuple[str, str, str, str], ...]:
    """Keep an explicit unresolved record instead of silently omitting a division."""

    raw_records = payload.get("unresolved")
    if not isinstance(raw_records, list):
        raise ValueError("Division turnout evidence must contain an unresolved list.")
    unresolved = []
    for item in raw_records:
        record = _mapping(item, "unresolved turnout record")
        division_name = _required_text(record, "division_name")
        if division_name not in divisions:
            raise ValueError(
                "Unresolved evidence does not use an exact official division name: "
                f"{division_name}."
            )
        unresolved.append(
            (
                division_name,
                _required_text(record, "source_division_name"),
                _required_text(record, "source_url"),
                _required_text(record, "reason"),
            )
        )
    return tuple(unresolved)


def _accepted_ballot_papers_issued(
    payload: Mapping[str, object],
    divisions: Mapping[str, str],
    records: Sequence[CandidateResultRecord],
) -> tuple[tuple[str, str, int, str, Mapping[str, str]], ...]:
    """Accept only declaration values anchored by an exact name and electorate.

    A local returning-officer declaration can be authoritative for its own
    divisions, but it must still agree with the County result page on the
    published electorate. A disagreement leaves the value unresolved instead
    of assuming that either source's ballot-paper count is transferable.
    """

    ballot_section = _mapping(payload.get("ballot_papers_issued"), "ballot_papers_issued")
    source = _mapping(ballot_section.get("source"), "ballot_papers_issued source")
    raw_records = ballot_section.get("accepted_records")
    if not isinstance(raw_records, list):
        raise ValueError("Ballot-papers-issued evidence must contain an accepted_records list.")
    electorates = _official_electorates(records)
    accepted = []
    seen_names: set[str] = set()
    for item in raw_records:
        record = _mapping(item, "ballot-papers-issued evidence record")
        division_name = _required_text(record, "division_name")
        if division_name not in divisions:
            raise ValueError(
                "Ballot-papers-issued evidence does not use an exact official division name: "
                f"{division_name}."
            )
        if division_name in seen_names:
            raise ValueError(f"Duplicate ballot-papers-issued evidence for {division_name}.")
        value = record.get("value")
        source_electorate = record.get("source_electorate")
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"Ballot-papers-issued value must be a non-negative integer for {division_name}.")
        if not isinstance(source_electorate, int) or source_electorate < 1:
            raise ValueError(f"Source electorate must be a positive integer for {division_name}.")
        if electorates[division_name] != source_electorate:
            raise ValueError(
                "Ballot-papers-issued evidence electorate conflicts with the official "
                f"Surrey result page for {division_name}."
            )
        seen_names.add(division_name)
        accepted.append(
            (
                division_name,
                divisions[division_name],
                value,
                _required_text(record, "source_division_name"),
                {key: _required_text(source, key) for key in (
                    "source_type", "source_name", "source_url", "retrieval_date", "confidence", "validation_status"
                )},
            )
        )
    return tuple(accepted)


def _official_electorates(
    records: Sequence[CandidateResultRecord],
) -> dict[str, int]:
    """Return one shared published electorate for each official division page."""

    values_by_name: defaultdict[str, set[int]] = defaultdict(set)
    for record in records:
        if record.division_ward_name is None or record.electorate is None:
            raise ValueError("Ballot evidence requires published official division names and electorates.")
        values_by_name[record.division_ward_name].add(record.electorate)
    electorates = {}
    for division_name, values in values_by_name.items():
        if len(values) != 1:
            raise ValueError(f"Division {division_name} has conflicting official electorates.")
        electorates[division_name] = next(iter(values))
    return electorates


def _validate_coverage(
    divisions: Mapping[str, str],
    accepted: Sequence[tuple[str, str, float, str]],
    unresolved: Sequence[tuple[str, str, str, str]],
) -> None:
    """Require every official division to be accepted or explicitly unresolved."""

    reviewed = {item[0] for item in accepted} | {item[0] for item in unresolved}
    missing = sorted(set(divisions) - reviewed)
    duplicate = {item[0] for item in accepted} & {item[0] for item in unresolved}
    if missing or duplicate:
        raise ValueError(
            "Division turnout audit coverage is incomplete or duplicated: "
            f"missing={missing}, duplicate={sorted(duplicate)}."
        )


def _turnout_metadata_record(
    *,
    division_name: str,
    division_id: str,
    value: float,
    source_division_name: str,
    source: Mapping[str, str],
) -> SupplementaryMetadataRecord:
    """Create an additive record with an explicit source heading and value."""

    return SupplementaryMetadataRecord(
        metadata_id=f"{division_id}:secondary_division_turnout:surrey-council",
        election_id="surrey-county-council-2013",
        division_id=division_id,
        field_name="secondary_division_turnout",
        value=value,
        geographic_level=GeographicLevel.DIVISION,
        source_type=source["source_type"],
        source_name=source["source_name"],
        source_url=source["source_url"],
        evidence_text=(
            f"The official result section ‘RESULT - {source_division_name}’ "
            f"states ‘Turnout {value:g}%’."
        ),
        retrieval_date=source["retrieval_date"],
        confidence=source["confidence"],
        notes=(
            "Supplementary division evidence only. It does not populate the "
            "official turnout field or change division completeness."
        ),
        validation_status=SupplementaryValidationStatus(source["validation_status"]),
    )


def _ballot_papers_issued_metadata_record(
    *,
    division_name: str,
    division_id: str,
    value: int,
    source_division_name: str,
    source: Mapping[str, str],
) -> SupplementaryMetadataRecord:
    """Create additive ballot-paper evidence without changing the official cell."""

    return SupplementaryMetadataRecord(
        metadata_id=f"{division_id}:secondary_division_ballot_papers_issued:woking",
        election_id="surrey-county-council-2013",
        division_id=division_id,
        field_name="secondary_division_ballot_papers_issued",
        value=value,
        geographic_level=GeographicLevel.DIVISION,
        source_type=source["source_type"],
        source_name=source["source_name"],
        source_url=source["source_url"],
        evidence_text=(
            f"The official Woking declaration for {source_division_name} states "
            f"‘Ballot Papers Issued: {value:,}’."
        ),
        retrieval_date=source["retrieval_date"],
        confidence=source["confidence"],
        notes=(
            "Supplementary division evidence only. The named Woking declaration's "
            "electorate was cross-checked against the official Surrey result page; "
            "this value does not populate the official ballot_papers_issued field or "
            "change division completeness."
        ),
        validation_status=SupplementaryValidationStatus(source["validation_status"]),
    )


def _ballot_reason(payload: Mapping[str, object]) -> str:
    """Keep the evidence-register reason in every unresolved ballot field row."""

    ballot_section = _mapping(payload.get("ballot_papers_issued"), "ballot_papers_issued")
    return _required_text(ballot_section, "unresolved_reason")


def _division_id(source_url: str) -> str:
    """Derive the existing stable 2013 division ID from an official URL."""

    result_id = parse_qs(urlsplit(source_url).query).get("ID", [None])[0]
    if not result_id:
        raise ValueError(f"Official result URL has no ID parameter: {source_url}")
    return f"surrey-county-council-2013:result:{result_id}"


def _mapping(value: object, label: str) -> Mapping[str, object]:
    """Fail early when a hand-reviewed evidence register is malformed."""

    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object.")
    return value


def _required_text(record: Mapping[str, object], field_name: str) -> str:
    """Read required audit text without substituting placeholder values."""

    value = record.get(field_name)
    if value is None or not str(value).strip():
        raise ValueError(f"Audit record requires {field_name}.")
    return str(value).strip()
