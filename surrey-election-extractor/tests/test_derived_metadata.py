"""Tests for calculated values that remain separate from official evidence."""

from dataclasses import replace
from pathlib import Path

import pytest

from election_extractor.derived_metadata import (
    derive_records_from_rules,
    load_derived_metadata,
    load_derived_metadata_rules,
    validate_derived_metadata,
)
from election_extractor.master_database import (
    build_master_database,
    load_audited_elections,
)


REIGATE_ELECTION_ID = "surrey-county-council-2017"
REIGATE_DIVISION_ID = "surrey-county-council-2017:result:230"
REIGATE_URL = (
    "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?"
    "ID=230&RPID=454155221&XXR=0"
)


def derived_record():
    """Load the one committed calculation used in the master database tests."""

    project_root = Path(__file__).resolve().parents[1]
    return load_derived_metadata(
        project_root / "config/derived_metadata.json",
        permitted_election_ids={REIGATE_ELECTION_ID},
    )[0]


def official_values(*, rejected_ballots: int | None = None) -> dict[str, dict[str, object]]:
    """Provide the exact published Reigate inputs without making an HTTP request."""

    return {
        REIGATE_DIVISION_ID: {
            "ballot_papers_issued": 4109,
            "total_votes": 4109,
            "rejected_ballots": rejected_ballots,
        }
    }


def official_urls() -> dict[str, str]:
    """Return the single official page required for both calculation inputs."""

    return {REIGATE_DIVISION_ID: REIGATE_URL}


def issued_rule():
    """Load the reviewed 2013 issued-ballot derivation rule from configuration."""

    project_root = Path(__file__).resolve().parents[1]
    return load_derived_metadata_rules(
        project_root / "config/derived_metadata.json",
        permitted_election_ids={"surrey-county-council-2013"},
    )[0]


def test_derived_record_requires_matching_official_inputs_and_formula() -> None:
    """The committed result is reproducible from two values on one official page."""

    record = derived_record()
    validate_derived_metadata(
        (record,),
        official_values_by_division=official_values(),
        official_source_urls_by_division=official_urls(),
    )

    assert record.field_name == "derived_rejected_ballots"
    assert record.value == 0
    assert record.formula == "ballot_papers_issued - total_votes"


def test_derived_record_is_rejected_when_a_source_input_or_url_differs() -> None:
    """A config value cannot stand in for an absent or different official input."""

    record = derived_record()
    with pytest.raises(ValueError, match="does not match the official result value"):
        validate_derived_metadata(
            (record,),
            official_values_by_division={
                REIGATE_DIVISION_ID: {
                    "ballot_papers_issued": 4108,
                    "total_votes": 4109,
                    "rejected_ballots": None,
                }
            },
            official_source_urls_by_division=official_urls(),
        )

    with pytest.raises(ValueError, match="same official result URL"):
        validate_derived_metadata(
            (replace(record, source_url="https://example.invalid/result"),),
            official_values_by_division=official_values(),
            official_source_urls_by_division=official_urls(),
        )


def test_derived_record_cannot_replace_a_published_official_target() -> None:
    """A calculation is forbidden as soon as the official target has a value."""

    with pytest.raises(ValueError, match="officially published target field"):
        validate_derived_metadata(
            (derived_record(),),
            official_values_by_division=official_values(rejected_ballots=0),
            official_source_urls_by_division=official_urls(),
        )


def test_master_database_exports_derived_value_without_changing_reigate() -> None:
    """The exported calculation leaves the official NULL and completeness intact."""

    payload = build_master_database(load_audited_elections())
    reigate = next(
        row
        for row in payload.divisions_and_wards
        if row["election_id"] == REIGATE_ELECTION_ID
        and row["division_name"] == "Reigate"
    )
    derived = next(
        row
        for row in payload.derived_metadata
        if row["division_id"] == REIGATE_DIVISION_ID
    )

    assert reigate["rejected_ballots"] is None
    assert reigate["division_completeness_status"] == "incomplete"
    assert derived["value"] == 0
    assert derived["official_inputs"] == "ballot_papers_issued=4109; total_votes=4109"


def test_2013_rule_derives_issued_only_from_missing_target_and_same_page_inputs() -> None:
    """The rule skips published targets and does not accept a missing input."""

    rule = issued_rule()
    generated = derive_records_from_rules(
        (rule,),
        official_values_by_division={
            "division-a": {
                "number_of_seats": 1,
                "total_votes": 2891,
                "rejected_ballots": 9,
                "ballot_papers_issued": None,
            },
            "division-b": {
                "number_of_seats": 1,
                "total_votes": 3065,
                "rejected_ballots": None,
                "ballot_papers_issued": None,
            },
            "division-c": {
                "number_of_seats": 1,
                "total_votes": 1721,
                "rejected_ballots": 16,
                "ballot_papers_issued": 1737,
            },
            "division-d": {
                "number_of_seats": 2,
                "total_votes": 4000,
                "rejected_ballots": 10,
                "ballot_papers_issued": None,
            },
        },
        official_source_urls_by_division={
            "division-a": "https://example.test/result-a",
            "division-b": "https://example.test/result-b",
            "division-c": "https://example.test/result-c",
            "division-d": "https://example.test/result-d",
        },
    )

    assert len(generated) == 1
    assert generated[0].division_id == "division-a"
    assert generated[0].value == 2900
    assert generated[0].source_url == "https://example.test/result-a"
    assert generated[0].formula == "total_votes + rejected_ballots"


def test_master_database_exports_all_2013_derived_issued_values_separately() -> None:
    """All 81 values remain calculated metadata, not official source fields."""

    payload = build_master_database(load_audited_elections())
    derived = [
        row
        for row in payload.derived_metadata
        if row["election_id"] == "surrey-county-council-2013"
        and row["field_name"] == "derived_ballot_papers_issued"
    ]
    addlestone = next(
        row
        for row in payload.divisions_and_wards
        if row["election_id"] == "surrey-county-council-2013"
        and row["division_name"] == "Addlestone"
    )
    addlestone_derived = next(
        row for row in derived if row["division_id"] == addlestone["division_id"]
    )

    assert len(derived) == 81
    assert addlestone["ballot_papers_issued"] is None
    assert addlestone["division_completeness_status"] == "incomplete"
    assert addlestone_derived["value"] == 2900
    assert addlestone_derived["official_inputs"] == (
        "rejected_ballots=9; total_votes=2891"
    )
