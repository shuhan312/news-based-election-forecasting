"""Tests for the source-preserving historical-to-2026 mapping evidence audit."""

from __future__ import annotations

from pathlib import Path

from election_extractor.election_config import ElectionConfiguration
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus
from election_extractor.geographic_mapping_audit import (
    GeographicMappingAuditConfiguration,
    GeographicMappingAuditStatus,
    MappingEvidenceSource,
    build_geographic_mapping_audit,
)
from election_extractor.master_database import AuditedElectionInput


def audited_election(election_id: str, year: int, area_name: str) -> AuditedElectionInput:
    """Build one minimal audited input with a published area name and URL."""

    configuration = ElectionConfiguration(
        election_id=election_id,
        election_name=f"Surrey Election {year}",
        election_year=year,
        election_type="County Council election",
        official_url=f"https://example.test/{election_id}",
        official_url_field="official_url",
    )
    record = CandidateResultRecord(
        election_name=None,
        election_date="7 May 2026",
        authority="Surrey County Council",
        division_ward_name=area_name,
        number_of_seats=2,
        candidate_name="Candidate One",
        original_party_name="Independent",
        votes_received=100,
        vote_share=50.0,
        outcome="Elected",
        electorate=1000,
        ballot_papers_issued=500,
        ballot_papers_rejected=2,
        turnout=50.0,
        source_url=f"https://example.test/results?ID={year}",
        extraction_status=ExtractionStatus.INCOMPLETE,
        missing_fields=("election_name",),
    )
    return AuditedElectionInput(
        configuration=configuration,
        audit_path=Path(__file__),
        records=(record,),
        election_structure_metadata=(),
    )


def configuration(*, has_crosswalk: bool = False) -> GeographicMappingAuditConfiguration:
    """Create a source register that explicitly states its mapping capability."""

    return GeographicMappingAuditConfiguration(
        audit_id="mapping-audit",
        previous_election_ids=("surrey-county-council-2021",),
        current_election_ids=(
            "surrey-county-council-2026-east-surrey",
            "surrey-county-council-2026-west-surrey",
        ),
        sources=(
            MappingEvidenceSource(
                source_name="Official structural document",
                source_type="Official document",
                source_url="https://example.test/structure",
                evidence_scope="Structure only",
                evidence_text="Describes new councils but no ward crosswalk.",
                direct_area_crosswalk_available=has_crosswalk,
            ),
        ),
    )


def test_structure_evidence_does_not_create_geographic_mappings() -> None:
    """Similar or changed areas remain unmapped without an explicit crosswalk."""

    audit = build_geographic_mapping_audit(
        (
            audited_election("surrey-county-council-2021", 2021, "Ash"),
            audited_election("surrey-county-council-2026-east-surrey", 2026, "Ash Ward"),
            audited_election("surrey-county-council-2026-west-surrey", 2026, "Ash Ward"),
        ),
        configuration(),
    )

    assert audit["status"] == GeographicMappingAuditStatus.REQUIRES_AUTHORITATIVE_CROSSWALK.value
    assert audit["verified_geographic_mapping_rows"] == []
    assert audit["assessment"]["historical_comparisons_allowed"] is False
    assert audit["current_election_coverage"][0]["area_count"] == 1


def test_registered_crosswalk_still_requires_separate_manual_mapping_review() -> None:
    """A source register cannot turn evidence availability into invented rows."""

    audit = build_geographic_mapping_audit(
        (
            audited_election("surrey-county-council-2021", 2021, "Example Division"),
            audited_election("surrey-county-council-2026-east-surrey", 2026, "Example Ward"),
            audited_election("surrey-county-council-2026-west-surrey", 2026, "Other Ward"),
        ),
        configuration(has_crosswalk=True),
    )

    assert audit["status"] == GeographicMappingAuditStatus.CROSSWALK_REVIEW_REQUIRED.value
    assert audit["verified_geographic_mapping_rows"] == []
    assert audit["assessment"]["historical_comparisons_allowed"] is False
