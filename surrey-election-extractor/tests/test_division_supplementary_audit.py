"""Tests for the reviewed 2013 division-level evidence boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from election_extractor.division_supplementary_audit import (
    audit_2013_division_evidence,
)
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = PROJECT_ROOT / "config/2013_division_turnout_evidence.json"


def _official_records() -> tuple[CandidateResultRecord, ...]:
    """Create one official-like record per reviewed division for exact matching."""

    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    names = [item["division_name"] for item in payload["records"]]
    names.extend(item["division_name"] for item in payload["unresolved"])
    names.append(
        payload["wikipedia_cross_validated_turnout"]["accepted_record"]["division_name"]
    )
    ballot_electorates = {
        item["division_name"]: item["source_electorate"]
        for item in payload["ballot_papers_issued"]["accepted_records"]
    }
    # The Byfleets is intentionally not an accepted declaration record: this
    # fixture uses the published Surrey electorate to exercise the discrepancy
    # guard in a focused test below.
    ballot_electorates["The Byfleets"] = 10019
    return tuple(
        CandidateResultRecord(
            election_name="Surrey County Council Election 2013",
            election_date="2 May 2013",
            authority="Surrey County Council",
            division_ward_name=name,
            number_of_seats=1,
            candidate_name=f"Candidate {index}",
            original_party_name="Example Party",
            votes_received=100,
            vote_share=50.0,
            outcome="Elected",
            electorate=ballot_electorates.get(name, 1000),
            ballot_papers_issued=None,
            ballot_papers_rejected=2,
            turnout=None,
            source_url=(
                "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx"
                f"?ID={index}&RPID=5"
            ),
            extraction_status=ExtractionStatus.INCOMPLETE,
            missing_fields=("ballot_papers_issued", "turnout"),
        )
        for index, name in enumerate(names, start=1)
    )


def test_named_turnout_evidence_is_separate_from_official_fields() -> None:
    """Only explicit named Council values enter the supplementary layer."""

    records = _official_records()
    audit = audit_2013_division_evidence(records)

    assert audit.report["summary"] == {
        "official_divisions_audited": 81,
        "accepted_supplementary_division_turnout": 81,
        "accepted_official_division_turnout": 80,
        "accepted_cross_validated_wikipedia_division_turnout": 1,
        "unresolved_division_turnout": 0,
        "accepted_supplementary_ballot_papers_issued": 6,
        "unresolved_ballot_papers_issued": 75,
    }
    assert len(audit.supplementary_records) == 87
    assert all(record.geographic_level.value == "division" for record in audit.supplementary_records)
    assert sum(
        record.field_name == "secondary_division_turnout"
        for record in audit.supplementary_records
    ) == 81
    ballot_records = [
        record
        for record in audit.supplementary_records
        if record.field_name == "secondary_division_ballot_papers_issued"
    ]
    assert {record.value for record in ballot_records} == {2796, 3198, 3336, 3642, 3728, 4062}
    assert all(record.turnout is None for record in records)
    assert all(record.ballot_papers_issued is None for record in records)


def test_cross_validated_wikipedia_turnout_is_separate_from_official_fields() -> None:
    """Wikipedia is accepted only as a separate record after ten cross-checks."""

    audit = audit_2013_division_evidence(_official_records())
    foxhills = next(
        item
        for item in audit.report["records"]
        if item["division_name"] == "Foxhills, Thorpe & Virginia Water"
    )

    assert foxhills["supplementary_turnout_available"] is True
    assert foxhills["supplementary_turnout_value"] == 27.0
    assert foxhills["turnout_status"] == "accepted"
    assert "wikipedia.org" in foxhills["turnout_source_url"]
    metadata = next(
        record
        for record in audit.supplementary_records
        if record.division_id == "surrey-county-council-2013:result:81"
        and record.field_name == "secondary_division_turnout"
    )
    assert metadata.value == 27.0
    assert metadata.source_type == "Wikipedia secondary election table"
    assert all(record.turnout is None for record in _official_records())


def test_wikipedia_turnout_requires_ten_matching_official_cross_checks(
    tmp_path: Path,
) -> None:
    """A changed Wikipedia value cannot be accepted without the required audit trail."""

    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    payload["wikipedia_cross_validated_turnout"]["cross_validation_records"] = payload[
        "wikipedia_cross_validated_turnout"
    ]["cross_validation_records"][:9]
    evidence_path = tmp_path / "insufficient-cross-checks.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="fewer verified cross-checks"):
        audit_2013_division_evidence(_official_records(), evidence_path)


def test_byfleets_source_disagreement_stays_unresolved() -> None:
    """A conflicting official electorate prevents importing the issued count."""

    audit = audit_2013_division_evidence(_official_records())
    byfleets = next(
        item for item in audit.report["records"] if item["division_name"] == "The Byfleets"
    )

    assert byfleets["supplementary_ballot_papers_issued_available"] is False
    assert byfleets["supplementary_ballot_papers_issued"] is None
    assert byfleets["ballot_papers_issued_status"] == "unresolved"
    assert "10,016" in byfleets["ballot_papers_issued_reason"]


def test_unreviewed_official_division_is_rejected() -> None:
    """The audit cannot silently omit a division that lacks reviewed evidence."""

    records = _official_records() + (
        CandidateResultRecord(
            election_name="Surrey County Council Election 2013",
            election_date="2 May 2013",
            authority="Surrey County Council",
            division_ward_name="Unreviewed Division",
            number_of_seats=1,
            candidate_name="Candidate 82",
            original_party_name="Example Party",
            votes_received=100,
            vote_share=50.0,
            outcome="Elected",
            electorate=1000,
            ballot_papers_issued=None,
            ballot_papers_rejected=2,
            turnout=None,
            source_url="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=82&RPID=5",
            extraction_status=ExtractionStatus.INCOMPLETE,
            missing_fields=("ballot_papers_issued", "turnout"),
        ),
    )

    with pytest.raises(ValueError, match="missing=.*Unreviewed Division"):
        audit_2013_division_evidence(records)
