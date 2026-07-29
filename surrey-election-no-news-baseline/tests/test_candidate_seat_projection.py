"""Tests for the predicted winning party and party seat totals.

The projection is the output a reader checks against the real council, so the
tests are about the cases where a naive implementation quietly gets it wrong:
a two-member ward won twice by one party, a tie sitting exactly on the seat
boundary, and a party that the model awarded seats to but which won none.
"""

from __future__ import annotations

from no_news_baseline.candidate_seat_projection import (
    contest_projections,
    party_seat_totals,
    seat_projection_summary,
)


def candidate(party, share, *, elected=False, seats=1, division="d1",
              election="e1", reform=False, row_id=None):
    return {
        "candidate_contest_id": row_id or f"{division}-{party}-{share}",
        "election_id": election,
        "division_id": division,
        "election_date": "7 May 2026",
        "contest_structure": "single_member" if seats == 1 else "multi_member",
        "standard_party_name": party,
        "is_reform_uk": reform,
        "analysis_number_of_seats": seats,
        "predicted_vote_share": share,
        "observed_elected": elected,
    }


# ---------------------------------------------------------------------------
# Contest projections
# ---------------------------------------------------------------------------


def test_single_member_contest_names_the_top_party():
    rows = [
        candidate("Conservative", 40.0, elected=True),
        candidate("Labour", 35.0),
        candidate("Reform UK", 25.0, reform=True),
    ]
    projection = contest_projections(rows)[0]
    assert projection["predicted_winning_parties"] == "Conservative"
    assert projection["observed_winning_parties"] == "Conservative"
    assert projection["winning_parties_correct"] is True


def test_a_wrong_call_is_recorded_as_wrong():
    rows = [
        candidate("Conservative", 40.0),
        candidate("Reform UK", 35.0, elected=True, reform=True),
    ]
    projection = contest_projections(rows)[0]
    assert projection["predicted_winning_parties"] == "Conservative"
    assert projection["observed_winning_parties"] == "Reform UK"
    assert projection["winning_parties_correct"] is False


def test_two_member_ward_won_twice_by_one_party_reports_it_once_as_a_party():
    """The party set has one entry; the seat count must still be two."""

    rows = [
        candidate("Conservative", 30.0, seats=2, elected=True, row_id="a"),
        candidate("Conservative", 28.0, seats=2, elected=True, row_id="b"),
        candidate("Labour", 22.0, seats=2, row_id="c"),
        candidate("Reform UK", 20.0, seats=2, reform=True, row_id="d"),
    ]
    projection = contest_projections(rows)[0]
    assert projection["predicted_winning_parties"] == "Conservative"
    assert len(projection["predicted_winning_candidates"].split("|")) == 2

    totals = {t["standard_party_name"]: t for t in party_seat_totals(rows)}
    assert totals["Conservative"]["predicted_seats"] == 2


def test_a_split_ward_names_both_parties():
    rows = [
        candidate("Conservative", 30.0, seats=2, elected=True, row_id="a"),
        candidate("Reform UK", 28.0, seats=2, elected=True, reform=True, row_id="b"),
        candidate("Labour", 22.0, seats=2, row_id="c"),
    ]
    projection = contest_projections(rows)[0]
    assert projection["predicted_winning_parties"] == "Conservative|Reform UK"
    assert projection["reform_predicted_elected"] is True


def test_a_tie_on_the_seat_boundary_is_recorded_not_broken():
    """Breaking it would manufacture a prediction the model did not make."""

    rows = [
        candidate("Conservative", 40.0, elected=True, row_id="a"),
        candidate("Labour", 30.0, row_id="b"),
        candidate("Reform UK", 30.0, reform=True, row_id="c"),
    ]
    # One seat, so the boundary sits above Labour and Reform equally.
    projection = contest_projections(rows)[0]
    assert projection["tie_at_seat_boundary"] is False  # boundary is at 40, alone

    tied = [
        candidate("Labour", 35.0, elected=True, row_id="a"),
        candidate("Reform UK", 35.0, reform=True, row_id="b"),
        candidate("Conservative", 20.0, row_id="c"),
    ]
    projection = contest_projections(tied)[0]
    assert projection["tie_at_seat_boundary"] is True
    assert "Reform UK" in projection["tied_parties_at_boundary"]


def test_a_contest_with_no_observed_result_is_not_scored():
    """Out-of-fold rows for an unresolved contest must not count as wrong."""

    rows = [candidate("Conservative", 40.0), candidate("Labour", 35.0)]
    projection = contest_projections(rows)[0]
    assert projection["winning_parties_correct"] is None
    assert seat_projection_summary(rows)["contests_scored"] == 0


# ---------------------------------------------------------------------------
# Party seat totals
# ---------------------------------------------------------------------------


def test_a_party_awarded_seats_it_did_not_win_appears_with_zero_observed():
    """It must not simply be absent from the table."""

    rows = [
        candidate("Conservative", 40.0),
        candidate("Reform UK", 35.0, elected=True, reform=True),
    ]
    totals = {t["standard_party_name"]: t for t in party_seat_totals(rows)}
    assert totals["Conservative"]["predicted_seats"] == 1
    assert totals["Conservative"]["observed_seats"] == 0
    assert totals["Conservative"]["seat_error"] == 1
    assert totals["Reform UK"]["seat_error"] == -1


def test_totals_are_reported_per_election_not_pooled():
    rows = [
        candidate("Conservative", 40.0, elected=True, election="e1", division="d1"),
        candidate("Labour", 30.0, election="e1", division="d1"),
        candidate("Labour", 40.0, elected=True, election="e2", division="d2"),
        candidate("Conservative", 30.0, election="e2", division="d2"),
    ]
    elections = {t["election_id"] for t in party_seat_totals(rows)}
    assert elections == {"e1", "e2"}


def test_summary_absolute_error_is_the_sum_of_the_table():
    rows = [
        candidate("Conservative", 40.0),
        candidate("Reform UK", 35.0, elected=True, reform=True),
    ]
    totals = party_seat_totals(rows)
    summary = seat_projection_summary(rows)
    assert summary["party_seat_total_absolute_error"] == sum(
        int(t["absolute_seat_error"]) for t in totals
    )


def test_reform_counts_are_reported_separately():
    rows = [
        candidate("Conservative", 40.0, elected=True),
        candidate("Reform UK", 35.0, reform=True),
    ]
    summary = seat_projection_summary(rows)
    assert summary["reform_uk"]["contests_predicted_elected"] == 0
    assert summary["reform_uk"]["contests_observed_elected"] == 0
