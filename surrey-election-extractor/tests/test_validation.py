"""Unit tests for read-only Surrey election result validation."""

from dataclasses import replace
from datetime import datetime, timezone

from election_extractor.extraction import CandidateResultRecord, ExtractionStatus
from election_extractor.validation import (
    PublishedVotingSummary,
    ValidationStatus,
    validate_election_results,
)


SOURCE_URL = (
    "https://mycouncil.surreycc.gov.uk/"
    "mgElectionAreaResults.aspx?ID=201&RPID=0"
)
VALIDATION_TIME = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def candidate(
    name: str,
    party: str | None,
    votes: int | None,
    share: float | None,
    outcome: str | None,
    **overrides: object,
) -> CandidateResultRecord:
    values = {
        "election_name": "2021 Surrey County Council election",
        "election_date": "6 May 2021",
        "authority": "Surrey County Council",
        "division_ward_name": "Addlestone",
        "number_of_seats": 1,
        "candidate_name": name,
        "original_party_name": party,
        "votes_received": votes,
        "vote_share": share,
        "outcome": outcome,
        "electorate": 10000,
        "ballot_papers_issued": 4000,
        "ballot_papers_rejected": 10,
        "turnout": 40.0,
        "source_url": SOURCE_URL,
        "extraction_status": ExtractionStatus.COMPLETE,
        "missing_fields": (),
    }
    values.update(overrides)
    return CandidateResultRecord(**values)


def valid_records() -> tuple[CandidateResultRecord, ...]:
    return (
        candidate("Candidate One", "Conservative", 1000, 50.0, "Elected"),
        candidate("Candidate Two", "Labour", 1000, 50.0, "Not elected"),
    )


def summary(total_votes: int | None = 2000, valid_votes: int | None = 2000) -> PublishedVotingSummary:
    return PublishedVotingSummary(
        source_url=SOURCE_URL,
        total_votes=total_votes,
        valid_votes=valid_votes,
    )


def validate(
    records: tuple[CandidateResultRecord, ...],
    summaries: tuple[PublishedVotingSummary, ...] | None = None,
):
    supplied_summaries = (summary(),) if summaries is None else summaries
    return validate_election_results(
        records,
        supplied_summaries,
        validation_timestamp=VALIDATION_TIME,
    )[0]


def event_for(result, rule: str):
    return [event for event in result.events if event.validation_rule == rule]


# Basic validation and immutability requirements.
def test_01_valid_election_result_passes_validation() -> None:
    result = validate(valid_records())

    assert result.validation_status is ValidationStatus.PASSED
    assert result.election_name == "2021 Surrey County Council election"
    assert result.election_year == 2021
    assert result.division_ward_name == "Addlestone"
    assert result.validation_timestamp == VALIDATION_TIME
    assert result.missing_fields == ()


def test_02_validation_does_not_modify_extracted_records() -> None:
    records = valid_records()
    original_records = tuple(replace(record) for record in records)

    validate(records)

    assert records == original_records


# Candidate vote-total validation requirements.
def test_03_candidate_vote_totals_match_published_totals() -> None:
    result = validate(valid_records())

    events = event_for(result, "candidate_vote_total")
    assert len(events) == 1
    assert events[0].result is ValidationStatus.PASSED


def test_04_candidate_vote_total_conflict_is_a_warning() -> None:
    records = tuple(replace(record, vote_share=40.0) for record in valid_records())
    result = validate(records, (summary(total_votes=2500, valid_votes=None),))

    assert result.validation_status is ValidationStatus.WARNING
    assert "Candidate vote totals do not match" in result.warnings[0]
    assert event_for(result, "candidate_vote_total")[0].result is ValidationStatus.WARNING


def test_05_missing_total_votes_are_handled_as_incomplete() -> None:
    result = validate(valid_records(), (summary(total_votes=None, valid_votes=None),))

    assert result.validation_status is ValidationStatus.INCOMPLETE
    assert "summary.total_votes" in result.missing_fields
    assert event_for(result, "candidate_vote_total")[0].result is ValidationStatus.INCOMPLETE


# Published vote-share validation and rounding requirements.
def test_06_vote_share_matches_calculated_value() -> None:
    result = validate(valid_records())

    assert all(event.result is ValidationStatus.PASSED for event in event_for(result, "vote_share"))


def test_07_whole_number_vote_share_rounding_is_accepted() -> None:
    records = (
        candidate("Candidate One", "Conservative", 448, 45.0, "Elected"),
        candidate("Candidate Two", "Labour", 552, 55.0, "Not elected"),
    )
    result = validate(records, (summary(total_votes=1000, valid_votes=1000),))

    assert all(event.result is ValidationStatus.PASSED for event in event_for(result, "vote_share"))


def test_08_incorrect_vote_share_is_detected() -> None:
    records = (
        replace(valid_records()[0], vote_share=60.0),
        valid_records()[1],
    )
    result = validate(records)

    assert result.validation_status is ValidationStatus.FAILED
    assert "vote_share" in result.failed_checks


# Turnout consistency and rounding requirements.
def test_09_turnout_matches_electorate_and_ballot_papers() -> None:
    result = validate(valid_records())

    assert event_for(result, "turnout")[0].result is ValidationStatus.PASSED


def test_10_turnout_rounding_difference_is_accepted() -> None:
    records = tuple(
        replace(record, electorate=1000, ballot_papers_issued=376, turnout=38.0)
        for record in valid_records()
    )
    result = validate(records)

    assert event_for(result, "turnout")[0].result is ValidationStatus.PASSED


def test_11_incorrect_turnout_is_detected() -> None:
    records = tuple(replace(record, turnout=50.0) for record in valid_records())
    result = validate(records)

    assert result.validation_status is ValidationStatus.FAILED
    assert "turnout" in result.failed_checks


# Required candidate and election-summary field checks.
def test_12_missing_candidate_name_is_detected() -> None:
    records = (replace(valid_records()[0], candidate_name=""), valid_records()[1])
    result = validate(records)

    assert result.validation_status is ValidationStatus.INCOMPLETE
    assert "candidate[1].candidate_name" in result.missing_fields


def test_13_missing_party_is_detected() -> None:
    records = (replace(valid_records()[0], original_party_name=None), valid_records()[1])
    result = validate(records)

    assert result.validation_status is ValidationStatus.INCOMPLETE
    assert "candidate[1].party" in result.missing_fields


def test_14_missing_vote_value_is_detected() -> None:
    records = (replace(valid_records()[0], votes_received=None), valid_records()[1])
    result = validate(records)

    assert result.validation_status is ValidationStatus.INCOMPLETE
    assert "candidate[1].votes" in result.missing_fields


def test_15_missing_turnout_is_detected() -> None:
    records = tuple(replace(record, turnout=None) for record in valid_records())
    result = validate(records)

    assert result.validation_status is ValidationStatus.INCOMPLETE
    assert "summary.turnout" in result.missing_fields


# Conflict preservation requirements.
def test_16_conflicting_values_are_recorded() -> None:
    records = (valid_records()[0], replace(valid_records()[1], turnout=41.0))
    result = validate(records)

    assert result.validation_status is ValidationStatus.WARNING
    assert any("Conflicting published values for turnout" in note for note in result.validation_notes)
    assert any("40.0" in note and "41.0" in note for note in result.validation_notes)


def test_17_conflicting_values_do_not_overwrite_original_data() -> None:
    records = (valid_records()[0], replace(valid_records()[1], turnout=41.0))
    original_turnout = tuple(record.turnout for record in records)

    validate(records)

    assert tuple(record.turnout for record in records) == original_turnout


# Extraction-status interaction requirements.
def test_18_incomplete_extraction_remains_incomplete() -> None:
    records = (
        replace(valid_records()[0], extraction_status=ExtractionStatus.INCOMPLETE),
        valid_records()[1],
    )
    result = validate(records)

    assert result.validation_status is ValidationStatus.INCOMPLETE
    assert event_for(result, "extraction_status")[0].result is ValidationStatus.INCOMPLETE


def test_19_failed_extraction_remains_failed() -> None:
    records = (
        replace(valid_records()[0], extraction_status=ExtractionStatus.SEARCH_FAILED),
        valid_records()[1],
    )
    result = validate(records)

    assert result.validation_status is ValidationStatus.FAILED
    assert event_for(result, "extraction_status")[0].result is ValidationStatus.FAILED
