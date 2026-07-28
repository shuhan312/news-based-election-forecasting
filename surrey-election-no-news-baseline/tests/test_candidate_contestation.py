"""Tests for the did-not-contest record.

The brief calls this "an important distinction": a party that did not stand
has not scored zero. These tests pin the distinction and the two judgement
calls the module makes about which non-contests are worth asserting.
"""

import pytest

from no_news_baseline.candidate_contestation import (
    CONTESTED,
    DID_NOT_CONTEST,
    build_contestation_records,
    contestation_summary,
    reform_contest_history,
)


def _row(
    row_id: str,
    election_id: str,
    division_id: str,
    party: str,
    *,
    date: str = "6 May 2021",
    category: str = "established",
    seats: int = 1,
) -> dict[str, object]:
    return {
        "candidate_contest_id": row_id,
        "election_id": election_id,
        "election_date": date,
        "division_id": division_id,
        "division_name": division_id.replace("-", " ").title(),
        "standard_party_name": party,
        "party_category": category,
        "is_reform_uk": party == "Reform UK",
        "is_ukip": party == "UK Independence Party",
        "contest_structure": "single_member" if seats == 1 else "multi_member",
        "analysis_number_of_seats": seats,
        "candidate_baseline_eligibility": "eligible_candidate_vote_share",
    }


def _release() -> list[dict[str, object]]:
    """Two 2021 divisions; Reform stands in one only. Plus a 2013 division
    from before Reform existed."""

    return [
        _row("a1", "2021", "div-a", "Conservative"),
        _row("a2", "2021", "div-a", "Labour"),
        _row("a3", "2021", "div-a", "Reform UK"),
        _row("b1", "2021", "div-b", "Conservative"),
        _row("b2", "2021", "div-b", "Labour"),
        _row("c1", "2013", "div-c", "Conservative", date="2 May 2013"),
        _row("c2", "2013", "div-c", "UK Independence Party", date="2 May 2013"),
    ]


# --- the distinction itself ----------------------------------------------


def test_a_party_that_did_not_stand_is_recorded_not_absent() -> None:
    """The whole point: absence becomes a queryable row."""

    records = build_contestation_records(_release())
    reform_b = next(
        r for r in records
        if r.standard_party_name == "Reform UK" and r.division_id == "div-b"
    )

    assert reform_b.contestation_status == DID_NOT_CONTEST
    assert reform_b.candidates_fielded == 0


def test_a_party_that_stood_is_recorded_contested_with_its_candidate_count() -> None:
    records = build_contestation_records(_release())
    reform_a = next(
        r for r in records
        if r.standard_party_name == "Reform UK" and r.division_id == "div-a"
    )

    assert reform_a.contestation_status == CONTESTED
    assert reform_a.candidates_fielded == 1


def test_a_party_fielding_two_candidates_in_a_two_seat_ward_is_counted_as_two() -> None:
    rows = [
        _row("m1", "2026", "ward-a", "Conservative", seats=2),
        _row("m2", "2026", "ward-a", "Conservative", seats=2),
        _row("m3", "2026", "ward-a", "Reform UK", seats=2),
    ]
    records = build_contestation_records(rows)
    conservative = next(r for r in records if r.standard_party_name == "Conservative")

    assert conservative.candidates_fielded == 2
    assert conservative.contest_structure == "multi_member"
    assert conservative.seats == 2


# --- the party universe ---------------------------------------------------


def test_a_party_absent_from_an_entire_election_gets_no_records_there() -> None:
    """Emitting "Reform did not contest" for 2013 would state a fact about a
    party that had not been founded."""

    records = build_contestation_records(_release())
    reform_2013 = [
        r for r in records if r.standard_party_name == "Reform UK" and r.election_id == "2013"
    ]
    assert reform_2013 == []

    # And symmetrically: UKIP stood only in 2013 here, so it gets no 2021 rows.
    ukip_2021 = [
        r for r in records
        if r.standard_party_name == "UK Independence Party" and r.election_id == "2021"
    ]
    assert ukip_2021 == []


def test_independents_are_excluded_by_default_but_the_choice_is_exposed() -> None:
    """Each independent is its own identity, so including them would assert
    that a named individual declined to stand in every division in Surrey."""

    rows = _release() + [
        _row("i1", "2021", "div-a", "Independent", category="independent")
    ]

    default = build_contestation_records(rows)
    assert not [r for r in default if r.standard_party_name == "Independent"]

    included = build_contestation_records(rows, exclude_independents=False)
    assert [r for r in included if r.standard_party_name == "Independent"]


def test_rows_outside_the_cohort_are_ignored() -> None:
    rows = _release() + [
        {**_row("x1", "2021", "div-c", "Green"),
         "candidate_baseline_eligibility": "excluded_no_observed_candidate_vote_share"}
    ]
    records = build_contestation_records(rows)
    assert not [r for r in records if r.standard_party_name == "Green"]


# --- summary --------------------------------------------------------------


def test_summary_reports_a_contest_rate_per_election() -> None:
    """The denominator the brief's distinction exists to protect: a mean share
    over contested divisions is not a mean over all divisions."""

    summary = contestation_summary(build_contestation_records(_release()))
    reform = summary["2021"]["reform_uk"]

    assert reform["divisions_contested"] == 1
    assert reform["divisions_not_contested"] == 1
    assert reform["contest_rate"] == pytest.approx(0.5)
    assert reform["candidates_fielded"] == 1


def test_reform_and_ukip_are_summarised_separately() -> None:
    summary = contestation_summary(build_contestation_records(_release()))

    assert summary["2013"]["ukip"]["divisions_contested"] == 1
    # Reform did not exist in 2013, so it has no coverage there at all.
    assert summary["2013"]["reform_uk"]["divisions_contested"] == 0
    assert summary["2013"]["reform_uk"]["contest_rate"] is None


def test_reform_history_is_ordered_and_covers_both_statuses() -> None:
    history = reform_contest_history(build_contestation_records(_release()))

    assert len(history) == 2
    assert {row["contestation_status"] for row in history} == {CONTESTED, DID_NOT_CONTEST}
    assert all(row["is_reform_uk"] for row in history)
