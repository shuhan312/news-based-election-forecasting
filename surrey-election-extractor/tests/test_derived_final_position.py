"""Tests for the separate, tie-preserving candidate vote-rank layer."""

import pytest

from election_extractor.derived_final_position import (
    derive_final_positions,
    validate_final_positions_against_official_outcomes,
)
from election_extractor.extraction import CandidateResultRecord, ExtractionStatus
from election_extractor.master_database import build_master_database, load_audited_elections


def _record(
    name: str,
    votes: int | None,
    *,
    outcome: str = "Not elected",
    seats: int | None = 2,
    final_position: int | None = None,
):
    """Create one official candidate row without relying on network access."""

    return CandidateResultRecord(
        election_name="Example election",
        election_date="1 May 2026",
        authority="Surrey County Council",
        division_ward_name="Example Division",
        number_of_seats=seats,
        candidate_name=name,
        original_party_name="Example Party",
        votes_received=votes,
        vote_share=None,
        outcome=outcome,
        electorate=None,
        ballot_papers_issued=None,
        ballot_papers_rejected=None,
        turnout=None,
        source_url="https://example.test/result",
        extraction_status=ExtractionStatus.COMPLETE,
        missing_fields=(),
        final_position=final_position,
    )


def test_final_positions_use_competition_ranks_and_preserve_ties() -> None:
    """Equal vote totals must not be broken by alphabetical or page order."""

    positions = derive_final_positions(
        election_id="example-election",
        records=(
            _record("A", 100),
            _record("B", 80),
            _record("C", 80),
            _record("D", 50),
        ),
    )

    assert [(item.candidate_name, item.value, item.tied) for item in positions] == [
        ("A", 1, False),
        ("B", 2, True),
        ("C", 2, True),
        ("D", 4, False),
    ]


def test_incomplete_or_officially_ranked_pages_are_not_rederived() -> None:
    """The calculation must never invent a rank from partial or duplicate data."""

    assert derive_final_positions(
        election_id="example-election",
        records=(_record("A", 100), _record("B", None)),
    ) == ()


def test_outcome_validation_accepts_a_tied_cutoff_but_rejects_a_contradiction() -> None:
    """Outcome checks validate ranks without using outcome to calculate them."""

    tied_records = (
        _record("Winner", 100, outcome="Elected", seats=1),
        _record("Tied challenger", 100, seats=1),
        _record("Third", 50, seats=1),
    )
    validate_final_positions_against_official_outcomes(
        records=tied_records,
        positions=derive_final_positions(
            election_id="example-election", records=tied_records
        ),
    )

    contradictory_records = (
        _record("Published winner", 90, outcome="Elected", seats=1),
        _record("Higher non-winner", 95, seats=1),
    )
    with pytest.raises(ValueError, match="contradicts the derived candidate vote order"):
        validate_final_positions_against_official_outcomes(
            records=contradictory_records,
            positions=derive_final_positions(
                election_id="example-election", records=contradictory_records
            ),
        )
    assert derive_final_positions(
        election_id="example-election",
        records=(_record("A", 100, final_position=1), _record("B", 80)),
    ) == ()
    assert derive_final_positions(
        election_id="example-election",
        records=(_record("Same name", 100), _record("Same name", 80)),
    ) == ()


def test_master_database_exports_rank_without_filling_official_rank() -> None:
    """A transparent vote rank remains distinct from the official field."""

    payload = build_master_database(load_audited_elections())
    row = next(
        item
        for item in payload.candidate_results
        if item["election_id"] == "surrey-county-council-2013"
        and item["division_name"] == "Addlestone"
    )

    assert row["final_position"] is None
    assert row["derived_final_position"] is not None
    assert row["derived_final_position_status"] == (
        "derived_competition_rank_from_complete_official_votes"
    )
