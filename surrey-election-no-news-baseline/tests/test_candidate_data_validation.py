"""Tests for seat, date and evidence-layer validation.

These checks exist to catch data problems, so the tests mostly construct
broken data and assert that the break is reported. A validator that has only
ever been run on data that passes is a validator nobody has tested.
"""

from __future__ import annotations

import pytest

from no_news_baseline.candidate_data_validation import (
    election_date_validation,
    seat_validation,
)
from no_news_baseline.candidate_evidence_layers import (
    DERIVED,
    EVIDENCE_LAYERS,
    LAYERS,
    NOT_A_VALUE,
    OFFICIAL,
    PER_ROW,
    assert_every_column_classified,
    evidence_layer_report,
    layer_of,
)
from no_news_baseline.candidate_leakage_audit import FEATURE_COLUMNS


def row(**overrides):
    base = {
        "candidate_contest_id": "c1",
        "election_id": "e1",
        "division_id": "d1",
        "election_date": "2 May 2013",
        "election_year": 2013,
        "analysis_number_of_seats": 1,
        "candidate_count_in_contest": 2,
        "contest_structure": "single_member",
    }
    base.update(overrides)
    return base


def contest(seats=1, candidates=2, structure="single_member", **overrides):
    return [
        row(candidate_contest_id=f"c{index}", analysis_number_of_seats=seats,
            candidate_count_in_contest=candidates, contest_structure=structure,
            **overrides)
        for index in range(candidates)
    ]


# ---------------------------------------------------------------------------
# Seats
# ---------------------------------------------------------------------------


def test_a_coherent_contest_passes():
    report = seat_validation(contest())
    assert report["all_checks_passed"]
    assert report["contests_checked"] == 1


def test_two_member_contest_passes():
    report = seat_validation(contest(seats=2, candidates=5, structure="multi_member"))
    assert report["all_checks_passed"]
    assert report["contest_counts_by_structure_and_seats"] == {"multi_member": {2: 1}}


def test_rows_of_one_contest_disagreeing_about_seats_is_reported():
    """The failure that would allocate a different number of seats per read."""

    rows = contest(seats=1, candidates=2)
    rows[1] = dict(rows[1], analysis_number_of_seats=2)
    report = seat_validation(rows)

    assert not report["all_checks_passed"]
    assert report["contests_with_inconsistent_seat_counts"][0]["seat_counts"] == [1, 2]


def test_zero_seats_is_reported():
    report = seat_validation(contest(seats=0))
    assert not report["all_checks_passed"]
    assert report["contests_with_non_positive_seats"] == ["e1|d1"]


def test_more_seats_than_candidates_is_reported():
    """Top-N allocation would return the whole ballot."""

    report = seat_validation(contest(seats=3, candidates=2, structure="multi_member"))
    assert not report["all_checks_passed"]
    finding = report["contests_with_more_seats_than_candidates"][0]
    assert finding["seats"] == 3 and finding["candidates"] == 2


def test_declared_candidate_count_disagreeing_with_rows_present_is_reported():
    rows = contest(seats=1, candidates=2)
    rows = [dict(r, candidate_count_in_contest=9) for r in rows]
    report = seat_validation(rows)
    assert not report["all_checks_passed"]
    assert any(
        "declared candidate count" in str(f.get("note", ""))
        for f in report["contests_with_more_seats_than_candidates"]
    )


def test_structure_label_disagreeing_with_seat_count_is_reported():
    """A stale structure label, which the target transform depends on."""

    report = seat_validation(contest(seats=2, candidates=4, structure="single_member"))
    assert not report["all_checks_passed"]
    finding = report["contests_where_structure_disagrees_with_seats"][0]
    assert finding["expected"] == "multi_member"


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


def test_a_coherent_date_passes():
    report = election_date_validation(contest())
    assert report["all_checks_passed"]
    assert report["earliest_polling_date"] == "2013-05-02"


def test_unparseable_date_is_reported_not_raised():
    """An unparseable date must not stop the report describing the rest."""

    report = election_date_validation(contest(election_date="not a date"))
    assert not report["all_checks_passed"]
    assert report["unparseable_dates"][0]["election_date"] == "not a date"


def test_date_outside_the_study_period_is_reported():
    report = election_date_validation(
        contest(election_date="2 May 1999", election_year=1999)
    )
    assert not report["all_checks_passed"]
    assert report["dates_outside_study_period"]


def test_one_election_with_two_dates_is_reported():
    """Two polling days for one election would split its contests across a fold."""

    rows = contest(candidates=2)
    rows[1] = dict(rows[1], election_date="3 May 2013")
    report = election_date_validation(rows)

    assert not report["all_checks_passed"]
    assert report["elections_with_more_than_one_date"]["e1"] == [
        "2013-05-02", "2013-05-03"
    ]
    assert report["contests_spanning_more_than_one_date"] == ["e1|d1"]


def test_election_year_disagreeing_with_the_date_is_reported():
    report = election_date_validation(contest(election_year=2017))
    assert not report["all_checks_passed"]
    assert report["rows_where_election_year_disagrees_with_date"][0][
        "election_year"] == 2017


# ---------------------------------------------------------------------------
# Evidence layers
# ---------------------------------------------------------------------------


def test_every_published_column_has_an_evidence_layer():
    """The guard that stops a new feature defaulting to a layer."""

    assert_every_column_classified()
    assert set(EVIDENCE_LAYERS) == set(FEATURE_COLUMNS)


def test_every_layer_is_one_of_the_declared_four():
    assert {layer for layer, _ in EVIDENCE_LAYERS.values()} <= set(LAYERS)


def test_every_classification_carries_a_reason():
    """'derived' without a rule is an assertion."""

    assert all(reason.strip() for _, reason in EVIDENCE_LAYERS.values())


def test_standardised_party_name_is_derived_not_official():
    """The classification the brief cares most about.

    The name on the official page is original_party_name. The standardised
    label is this project's mapping, and it is the mapping that keeps Reform
    UK and UKIP apart - a project decision, not a source fact.
    """

    assert layer_of("standard_party_name") == DERIVED
    assert layer_of("is_reform_uk") == DERIVED
    assert layer_of("is_ukip") == DERIVED
    assert layer_of("original_party_name") == NOT_A_VALUE


def test_interaction_terms_are_derived():
    assert layer_of("reform_x_party_county_strength_previous") == DERIVED


def test_fields_with_their_own_provenance_are_not_given_a_single_label():
    """Declaring one layer would be a claim about rows it is not true of."""

    assert layer_of("analysis_number_of_seats") == PER_ROW
    assert layer_of("analysis_previous_turnout") == PER_ROW


def test_a_directly_observed_field_is_official():
    assert layer_of("election_date") == OFFICIAL
    assert layer_of("previous_party_vote_share") == OFFICIAL


def test_identifiers_are_not_evidence_values():
    assert layer_of("candidate_id") == NOT_A_VALUE
    assert layer_of("election_id") == NOT_A_VALUE


def test_unclassified_column_raises_rather_than_defaulting():
    with pytest.raises(KeyError, match="no evidence layer"):
        layer_of("a_column_nobody_declared")


def test_report_counts_predictors_separately_from_all_columns():
    """Predictors are the set whose evidence quality affects a result."""

    report = evidence_layer_report()
    assert sum(report["counts_by_layer"].values()) == len(FEATURE_COLUMNS)
    assert report["predictor_counts_by_layer"][NOT_A_VALUE] == 0


def test_report_adds_per_row_provenance_when_rows_are_supplied():
    rows = [
        row(analysis_number_of_seats_provenance="official_result_page",
            analysis_previous_turnout_provenance="unavailable_no_approved_predecessor"),
        row(analysis_number_of_seats_provenance="supplementary_statutory_evidence",
            analysis_previous_turnout_provenance="official_result_page"),
    ]
    report = evidence_layer_report(rows)
    assert report["per_row_provenance"]["analysis_number_of_seats"] == {
        "official_result_page": 1,
        "supplementary_statutory_evidence": 1,
    }
