"""Tests for the additive supplementary metadata governance layer."""

from dataclasses import replace
from pathlib import Path

import pytest

from election_extractor.completeness import assess_layered_completeness
from election_extractor.election_config import ElectionConfiguration
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus
from election_extractor.master_database import AuditedElectionInput, build_master_database
from election_extractor.models import (
    GeographicLevel,
    SupplementaryMetadataRecord,
    SupplementaryValidationStatus,
)
from election_extractor.supplementary_metadata import load_supplementary_metadata


SURREY_TURNOUT_URL = "https://news.surreycc.gov.uk/2013/05/03/election-results-special/"
ADDLESTONE_BY_ELECTION_ID = "surrey-county-council-by-election-addlestone-2025-08-21"
STAINES_BY_ELECTION_ID = "surrey-county-council-by-election-staines-south-ashford-west-2016-05-05"


def turnout_metadata(**changes: object) -> SupplementaryMetadataRecord:
    """Create one reviewed county-wide turnout claim for focused tests."""

    values = {
        "metadata_id": "surrey-county-council-2013:secondary_election_turnout:test",
        "election_id": "surrey-county-council-2013",
        "division_id": None,
        "field_name": "secondary_election_turnout",
        "value": 30.0,
        "geographic_level": GeographicLevel.ELECTION,
        "source_type": "Surrey County Council official publication",
        "source_name": "Surrey News: Election results declared",
        "source_url": SURREY_TURNOUT_URL,
        "evidence_text": "Turnout 30% across all 81 divisions.",
        "retrieval_date": "2026-07-15",
        "confidence": "High",
        "notes": "Election-wide only; never copied to divisions.",
        "validation_status": SupplementaryValidationStatus.VERIFIED,
    }
    values.update(changes)
    return SupplementaryMetadataRecord(**values)


def configuration() -> ElectionConfiguration:
    """Create the approved 2013 election configuration without extra metadata."""

    return ElectionConfiguration(
        election_id="surrey-county-council-2013",
        election_name="Surrey County Council Election 2013",
        election_year=2013,
        election_type="County Council election",
        official_url="https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=5&RPID=0",
        official_url_field="official_archive_url",
    )


def official_record() -> CandidateResultRecord:
    """Create a 2013 official row with only the documented division gaps."""

    return CandidateResultRecord(
        election_name="Surrey County Council Election 2013",
        election_date="2 May 2013",
        authority="Surrey County Council",
        division_ward_name="Example Division",
        number_of_seats=1,
        candidate_name="Candidate One",
        original_party_name="Conservative",
        votes_received=100,
        vote_share=50.0,
        outcome="Elected",
        electorate=1000,
        ballot_papers_issued=None,
        ballot_papers_rejected=2,
        turnout=None,
        source_url="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=1&RPID=5",
        extraction_status=ExtractionStatus.INCOMPLETE,
        missing_fields=("ballot_papers_issued", "turnout"),
    )


def test_approved_2013_metadata_loads_with_two_independent_sources() -> None:
    """The 2013 register preserves Council and Commission provenance separately."""

    project_root = Path(__file__).resolve().parents[1]
    records = load_supplementary_metadata(
        project_root / "config/supplementary_metadata.json",
        permitted_election_ids={
            "surrey-county-council-2013",
            ADDLESTONE_BY_ELECTION_ID,
            STAINES_BY_ELECTION_ID,
        },
    )

    election_records = tuple(
        record
        for record in records
        if record.election_id == "surrey-county-council-2013"
    )
    assert len(election_records) == 2
    assert {record.source_name for record in election_records} == {
        "Surrey News: Election results declared",
        "Electoral Commission: Results and turnout at the May 2017 England local elections",
    }
    assert {record.value for record in election_records} == {30.0}
    assert {record.geographic_level for record in election_records} == {GeographicLevel.ELECTION}


def test_by_election_turnout_is_registered_as_separate_division_metadata() -> None:
    """Each reviewed local-authority turnout claim keeps its own event and result scope."""

    project_root = Path(__file__).resolve().parents[1]
    records = load_supplementary_metadata(
        project_root / "config/supplementary_metadata.json",
        permitted_election_ids={
            "surrey-county-council-2013",
            ADDLESTONE_BY_ELECTION_ID,
            STAINES_BY_ELECTION_ID,
        },
    )
    addlestone = next(record for record in records if record.election_id == ADDLESTONE_BY_ELECTION_ID)

    assert addlestone.field_name == "secondary_division_turnout"
    assert addlestone.value == 24.0
    assert addlestone.division_id == f"{ADDLESTONE_BY_ELECTION_ID}:result:346"
    assert addlestone.geographic_level is GeographicLevel.DIVISION

    staines = next(record for record in records if record.election_id == STAINES_BY_ELECTION_ID)
    assert staines.field_name == "secondary_division_turnout"
    assert staines.value == 31.3
    assert staines.division_id == f"{STAINES_BY_ELECTION_ID}:result:8"
    assert staines.geographic_level is GeographicLevel.DIVISION


def test_supplementary_turnout_coexists_without_populating_official_division_field() -> None:
    """County-level evidence is visible separately and cannot repair a division."""

    source_record = official_record()
    payload = build_master_database(
        (
            AuditedElectionInput(
                configuration=configuration(),
                audit_path=Path(__file__),
                records=(source_record,),
                election_structure_metadata=(),
                supplementary_metadata=(turnout_metadata(),),
            ),
        )
    )
    layered = assess_layered_completeness(configuration(), (source_record,))

    assert payload.divisions_and_wards[0]["turnout"] is None
    assert payload.divisions_and_wards[0]["division_completeness_status"] == "incomplete"
    assert payload.supplementary_metadata[0]["value"] == 30.0
    assert payload.supplementary_metadata[0]["division_id"] is None
    assert layered.divisions[0].status.value == "incomplete"


def test_official_and_supplementary_values_coexist_in_separate_tables() -> None:
    """A documented external claim remains distinct even beside an official value."""

    source_record = official_record()
    secondary_seats = turnout_metadata(
        metadata_id="surrey-county-council-2013:result:1:secondary_number_of_seats",
        division_id="surrey-county-council-2013:result:1",
        field_name="secondary_number_of_seats",
        value=1,
        geographic_level=GeographicLevel.DIVISION,
        evidence_text="The supporting document names the division and one councillor.",
    )
    payload = build_master_database(
        (
            AuditedElectionInput(
                configuration=configuration(),
                audit_path=Path(__file__),
                records=(source_record,),
                election_structure_metadata=(),
                supplementary_metadata=(secondary_seats,),
            ),
        )
    )

    assert payload.divisions_and_wards[0]["official_number_of_seats"] == 1
    assert payload.supplementary_metadata[0]["value"] == 1
    assert payload.supplementary_metadata[0]["field_name"] == "secondary_number_of_seats"


def test_missing_official_values_remain_null_when_supplementary_metadata_exists() -> None:
    """External evidence never changes the audited official candidate record."""

    source_record = official_record()
    preserved = replace(source_record)
    payload = build_master_database(
        (
            AuditedElectionInput(
                configuration=configuration(),
                audit_path=Path(__file__),
                records=(source_record,),
                election_structure_metadata=(),
                supplementary_metadata=(turnout_metadata(),),
            ),
        )
    )

    assert source_record == preserved
    assert payload.divisions_and_wards[0]["ballot_papers_issued"] is None
    assert payload.divisions_and_wards[0]["turnout"] is None


@pytest.mark.parametrize("field_name", ["source_url", "evidence_text"])
def test_supplementary_values_require_source_url_and_evidence(field_name: str) -> None:
    """Every external value is rejected unless its provenance can be inspected."""

    with pytest.raises(ValueError, match=field_name):
        turnout_metadata(**{field_name: ""})
