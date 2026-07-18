"""Tests for the provenance-preserving analysis voting-summary layer."""

from election_extractor.analysis_voting_summary import build_analysis_voting_summary
from election_extractor.master_database import build_master_database, load_audited_elections
from scripts.generate_master_election_database import reviewed_historical_reference_inputs


def test_analysis_layer_uses_governed_precedence_without_filling_official_null() -> None:
    """Secondary and derived values must remain visibly distinct from official data."""

    rows = build_analysis_voting_summary(
        ({"election_id": "e", "division_id": "d", "division_name": "D", "official_number_of_seats": None, "secondary_number_of_seats": 2, "ballot_papers_issued": None, "turnout": None, "rejected_ballots": None},),
        ({"metadata_id": "s", "division_id": "d", "field_name": "secondary_division_turnout", "value": 40.0},),
        ({"metadata_id": "m", "division_id": "d", "field_name": "derived_ballot_papers_issued", "value": 100},),
    )
    values = {row["field_name"]: row for row in rows}
    assert values["analysis_number_of_seats"]["value"] == 2
    assert values["analysis_number_of_seats"]["provenance_layer"] == "supplementary_official_evidence"
    assert values["analysis_turnout"]["value"] == 40.0
    assert values["analysis_ballot_papers_issued"]["provenance_layer"] == "governed_derived_value"
    assert values["analysis_rejected_ballots"]["value"] is None


def test_analysis_margin_accepts_supplementary_single_seat_evidence() -> None:
    """Statutory Seats evidence can unlock analysis without filling official Seats."""

    rows = build_analysis_voting_summary(
        ({"election_id": "e", "division_id": "d", "division_name": "D", "official_number_of_seats": None, "secondary_number_of_seats": 1, "ballot_papers_issued": None, "turnout": None, "rejected_ballots": None, "winning_margin": None},),
        ({"metadata_id": "seat-evidence", "division_id": "d", "field_name": "secondary_number_of_seats", "value": 1},),
        (),
        (
            {"division_id": "d", "candidate_name": "Winner", "votes": 120, "outcome": "Elected"},
            {"division_id": "d", "candidate_name": "Runner-up", "votes": 95, "outcome": "Not elected"},
        ),
    )
    margin = next(row for row in rows if row["field_name"] == "analysis_winning_margin")

    assert margin["value"] == 25
    assert margin["provenance_layer"] == (
        "governed_derived_from_official_candidate_votes_and_supplementary_official_seats"
    )
    assert margin["source_metadata_id"] == "seat-evidence"


def test_published_official_margin_takes_precedence_without_recalculation() -> None:
    """A future official margin must pass through instead of being duplicated."""

    rows = build_analysis_voting_summary(
        ({"election_id": "e", "division_id": "d", "division_name": "D", "official_number_of_seats": 1, "secondary_number_of_seats": None, "ballot_papers_issued": None, "turnout": None, "rejected_ballots": None, "winning_margin": 24},),
        (),
        (),
        (
            {"division_id": "d", "candidate_name": "Winner", "votes": 120, "outcome": "Elected"},
            {"division_id": "d", "candidate_name": "Runner-up", "votes": 95, "outcome": "Not elected"},
        ),
    )
    margin = next(row for row in rows if row["field_name"] == "analysis_winning_margin")

    assert margin["value"] == 24
    assert margin["official_value"] == 24
    assert margin["provenance_layer"] == "official_result_page"


def test_analysis_margin_uses_last_seat_cutoff_for_multi_member_result() -> None:
    """The weakest elected candidate defines a reproducible final-seat margin."""

    rows = build_analysis_voting_summary(
        ({"election_id": "e", "division_id": "d", "division_name": "D", "official_number_of_seats": 2, "secondary_number_of_seats": None, "ballot_papers_issued": None, "turnout": None, "rejected_ballots": None, "winning_margin": None},),
        (),
        (),
        (
            {"division_id": "d", "candidate_name": "First", "votes": 120, "outcome": "Elected"},
            {"division_id": "d", "candidate_name": "Second", "votes": 110, "outcome": "Elected"},
            {"division_id": "d", "candidate_name": "Third", "votes": 100, "outcome": "Not elected"},
        ),
    )
    margin = next(row for row in rows if row["field_name"] == "analysis_winning_margin")

    assert margin["value"] == 10
    assert margin["provenance_layer"] == (
        "governed_derived_from_official_candidate_votes_and_official_seats"
    )


def test_release_has_audited_last_seat_analysis_margins_for_every_area() -> None:
    """Freeze complete coverage under one formula valid for one or more seats."""

    division_references, party_references = reviewed_historical_reference_inputs()
    payload = build_master_database(
        load_audited_elections(),
        historical_division_references=division_references,
        party_history_references=party_references,
    )
    margins = [
        row
        for row in payload.analysis_voting_summary
        if row["field_name"] == "analysis_winning_margin"
    ]

    assert len(margins) == 339
    assert sum(row["value"] is not None for row in margins) == 339
    assert sum(
        row["provenance_layer"]
        == "governed_derived_from_official_candidate_votes_and_official_seats"
        for row in margins
    ) == 311
    assert sum(
        row["provenance_layer"]
        == "governed_derived_from_official_candidate_votes_and_supplementary_official_seats"
        for row in margins
    ) == 28
    assert sum(row["value"] is None for row in margins) == 0

    # Every pre-existing same-page single-seat calculation must equal the new
    # analysis value. This proves that extending coverage did not change the
    # established 230 margins or introduce a competing single-seat formula.
    analysis_by_division = {row["division_id"]: row["value"] for row in margins}
    existing_derived = [
        row
        for row in payload.derived_metadata
        if row["field_name"] == "derived_winning_margin"
    ]
    assert len(existing_derived) == 230
    assert all(
        analysis_by_division[row["division_id"]] == row["value"]
        for row in existing_derived
    )
