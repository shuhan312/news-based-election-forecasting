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
            electorate=1000,
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
        "accepted_supplementary_division_turnout": 80,
        "unresolved_division_turnout": 1,
        "accepted_supplementary_ballot_papers_issued": 0,
        "unresolved_ballot_papers_issued": 81,
    }
    assert len(audit.supplementary_records) == 80
    assert all(record.geographic_level.value == "division" for record in audit.supplementary_records)
    assert all(record.field_name == "secondary_division_turnout" for record in audit.supplementary_records)
    assert all(record.turnout is None for record in records)
    assert all(record.ballot_papers_issued is None for record in records)


def test_unresolved_turnout_is_recorded_without_a_value() -> None:
    """A named section without a published number cannot create metadata."""

    audit = audit_2013_division_evidence(_official_records())
    foxhills = next(
        item
        for item in audit.report["records"]
        if item["division_name"] == "Foxhills, Thorpe & Virginia Water"
    )

    assert foxhills["supplementary_turnout_available"] is False
    assert foxhills["supplementary_turnout_value"] is None
    assert foxhills["turnout_status"] == "unresolved"


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
