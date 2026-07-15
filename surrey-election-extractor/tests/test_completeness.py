"""Tests for source-preserving layered election completeness assessment."""

from dataclasses import replace

from election_extractor.completeness import (
    CompletenessStatus,
    MetadataSource,
    assess_layered_completeness,
)
from election_extractor.election_config import ElectionConfiguration
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus


CONFIGURATION = ElectionConfiguration(
    election_id="surrey-county-council-2017",
    election_name="Surrey County Council Election 2017",
    election_year=2017,
    election_type="County Council election",
    official_url="https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=10&RPID=0",
    official_url_field="official_archive_url",
)
SOURCE_URL = "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=200&RPID=0"


def record(**overrides: object) -> CandidateResultRecord:
    """Build one complete official candidate result for layer-specific tests."""
    values = {
        "election_name": None,
        "election_date": "4 May 2017",
        "authority": "Surrey County Council",
        "division_ward_name": "Addlestone",
        "number_of_seats": 1,
        "candidate_name": "Candidate One",
        "original_party_name": "Conservative",
        "votes_received": 1000,
        "vote_share": 50.0,
        "outcome": "Elected",
        "electorate": 10000,
        "ballot_papers_issued": 4000,
        "ballot_papers_rejected": 10,
        "turnout": 40.0,
        "source_url": SOURCE_URL,
        "extraction_status": ExtractionStatus.INCOMPLETE,
        "missing_fields": ("election_name",),
    }
    values.update(overrides)
    return CandidateResultRecord(**values)


def field(assessment, name: str):
    """Find one assessed field without depending on output ordering in tests."""
    return next(item for item in assessment.fields if item.field_name == name)


def test_candidate_can_be_complete_when_election_name_is_missing() -> None:
    report = assess_layered_completeness(CONFIGURATION, (record(),))

    assert report.candidates[0].status is CompletenessStatus.COMPLETE
    assert report.candidates[0].missing_fields == ()
    assert report.election.status is CompletenessStatus.COMPLETE


def test_configuration_is_the_election_name_source() -> None:
    report = assess_layered_completeness(CONFIGURATION, (record(),))

    name = field(report.election, "election_name")
    assert name.value == "Surrey County Council Election 2017"
    assert name.source is MetadataSource.CONFIGURATION
    assert name.source_reference == "config/elections.json#surrey-county-council-2017"


def test_missing_rejected_ballots_affects_only_division_completeness() -> None:
    report = assess_layered_completeness(
        CONFIGURATION,
        (record(ballot_papers_rejected=None),),
    )

    assert report.candidates[0].status is CompletenessStatus.COMPLETE
    assert report.divisions[0].status is CompletenessStatus.INCOMPLETE
    assert report.divisions[0].missing_fields == ("ballot_papers_rejected",)


def test_missing_official_values_remain_missing() -> None:
    original = record(ballot_papers_rejected=None)
    report = assess_layered_completeness(CONFIGURATION, (original,))

    rejected = field(report.divisions[0], "ballot_papers_rejected")
    assert rejected.value is None
    assert rejected.source is MetadataSource.MISSING
    assert original.ballot_papers_rejected is None


def test_layered_assessment_does_not_overwrite_record_values() -> None:
    original = record(election_name="Page-specific election title")
    before = replace(original)
    report = assess_layered_completeness(CONFIGURATION, (original,))

    assert field(report.election, "election_name").value == CONFIGURATION.election_name
    assert original == before
    assert original.election_name == "Page-specific election title"
