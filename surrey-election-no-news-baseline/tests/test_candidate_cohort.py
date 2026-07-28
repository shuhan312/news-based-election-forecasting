"""Tests for the candidate-level cohort, normalisation and seat allocation."""

import math

import pytest

from no_news_baseline.candidate_cohort import (
    allocate_contest,
    assert_one_to_one_candidate_release,
    contest_key,
    contest_rounding_tolerance,
    group_by_contest,
    is_within_candidate_cohort,
    normalise_within_contest,
    reform_census,
    stratify_by_structure,
)


def _feature(
    candidate_contest_id: str,
    *,
    election_id: str = "2026-east",
    division_id: str = "ward-a",
    structure: str = "multi_member",
    eligibility: str = "eligible_candidate_vote_share",
    reform: bool = False,
    ukip: bool = False,
) -> dict[str, object]:
    return {
        "candidate_contest_id": candidate_contest_id,
        "election_id": election_id,
        "division_id": division_id,
        "contest_structure": structure,
        "candidate_baseline_eligibility": eligibility,
        "is_reform_uk": reform,
        "is_ukip": ukip,
    }


def _prediction(candidate_contest_id: str, value: float | None) -> dict[str, object]:
    return {
        "candidate_contest_id": candidate_contest_id,
        "predicted_candidate_vote_share": value,
    }


# --- release validation ---------------------------------------------------


def test_release_validation_returns_targets_indexed_by_id() -> None:
    features = [_feature("a"), _feature("b")]
    targets = [
        {"candidate_contest_id": "b"},
        {"candidate_contest_id": "a"},
    ]
    indexed = assert_one_to_one_candidate_release(features, targets)
    assert set(indexed) == {"a", "b"}


def test_release_validation_rejects_duplicate_identifiers() -> None:
    features = [_feature("a"), _feature("a")]
    targets = [{"candidate_contest_id": "a"}, {"candidate_contest_id": "a"}]
    with pytest.raises(ValueError, match="duplicate identifiers"):
        assert_one_to_one_candidate_release(features, targets)


def test_release_validation_rejects_mismatched_identifiers() -> None:
    features = [_feature("a")]
    targets = [{"candidate_contest_id": "b"}]
    with pytest.raises(ValueError, match="do not match"):
        assert_one_to_one_candidate_release(features, targets)


# --- cohort ---------------------------------------------------------------


def test_cohort_admits_multi_member_rows_without_history() -> None:
    """The behaviour the whole module exists for."""

    row = _feature("a", structure="multi_member")
    assert is_within_candidate_cohort(row)


def test_cohort_excludes_rows_the_extractor_labelled_ineligible() -> None:
    row = _feature("a", eligibility="excluded_no_observed_candidate_vote_share")
    assert not is_within_candidate_cohort(row)


def test_contest_grouping_uses_election_and_division() -> None:
    rows = [
        _feature("a", election_id="2026-east", division_id="ward-a"),
        _feature("b", election_id="2026-east", division_id="ward-a"),
        _feature("c", election_id="2026-west", division_id="ward-a"),
    ]
    grouped = group_by_contest(rows)

    assert contest_key(rows[0]) == ("2026-east", "ward-a")
    # Same division name in a different election is a different contest.
    assert len(grouped) == 2
    assert len(grouped[("2026-east", "ward-a")]) == 2


# --- normalisation --------------------------------------------------------


def test_normalisation_rescales_a_contest_to_one_hundred() -> None:
    predictions = [
        _prediction("a", 20.0),
        _prediction("b", 20.0),
        _prediction("c", 10.0),
    ]
    result = normalise_within_contest(predictions)

    assert math.isclose(sum(row.normalised_prediction for row in result), 100.0)
    assert all(row.normalisation_status == "normalised" for row in result)
    # The raw model output is preserved alongside the normalised value.
    assert [row.raw_prediction for row in result] == [20.0, 20.0, 10.0]
    assert math.isclose(result[0].normalised_prediction, 40.0)


def test_normalisation_clips_negative_predictions_before_rescaling() -> None:
    """A negative share is outside the target's support.

    Without clipping, a negative value would reduce the denominator and push
    the other candidates above their correct rescaled shares.
    """

    predictions = [_prediction("a", 60.0), _prediction("b", -10.0)]
    result = normalise_within_contest(predictions)

    assert math.isclose(result[0].normalised_prediction, 100.0)
    assert math.isclose(result[1].normalised_prediction, 0.0)
    # Raw values keep the sign the model actually produced.
    assert result[1].raw_prediction == -10.0


def test_normalisation_falls_back_to_an_equal_split_with_no_mass() -> None:
    predictions = [_prediction("a", 0.0), _prediction("b", -1.0)]
    result = normalise_within_contest(predictions)

    assert all(
        row.normalisation_status == "normalised_equal_split_zero_mass"
        for row in result
    )
    assert all(math.isclose(row.normalised_prediction, 50.0) for row in result)


def test_normalisation_refuses_a_partial_contest() -> None:
    predictions = [_prediction("a", 40.0), _prediction("b", None)]
    result = normalise_within_contest(predictions)

    assert all(row.normalised_prediction is None for row in result)
    assert all(
        row.normalisation_status == "not_normalised_missing_prediction"
        for row in result
    )


# --- allocation -----------------------------------------------------------


def test_two_member_ward_elects_two_candidates() -> None:
    """The multi-member seat rule, which the party cohort could not express."""

    predictions = [
        _prediction("a", 30.0),
        _prediction("b", 25.0),
        _prediction("c", 20.0),
        _prediction("d", 15.0),
    ]
    allocation = allocate_contest(predictions, seats=2)
    elected = {row.candidate_contest_id for row in allocation if row.predicted_elected}

    assert elected == {"a", "b"}
    assert all(row.allocation_status == "allocated" for row in allocation)
    ranks = {row.candidate_contest_id: row.predicted_rank for row in allocation}
    assert ranks == {"a": 1, "b": 2, "c": 3, "d": 4}


def test_single_member_contest_elects_one_candidate() -> None:
    predictions = [_prediction("a", 55.0), _prediction("b", 45.0)]
    allocation = allocate_contest(predictions, seats=1)
    elected = [row for row in allocation if row.predicted_elected]

    assert len(elected) == 1
    assert elected[0].candidate_contest_id == "a"


def test_tie_at_the_seat_cutoff_is_flagged_not_hidden() -> None:
    predictions = [
        _prediction("a", 40.0),
        _prediction("b", 30.0),
        _prediction("c", 30.0),
    ]
    allocation = allocate_contest(predictions, seats=2)

    assert all(
        row.allocation_status == "allocated_with_tie_at_cutoff" for row in allocation
    )
    tied = {row.candidate_contest_id for row in allocation if row.predicted_rank_tied}
    assert tied == {"b", "c"}
    # A choice is still made, deterministically, so reruns are reproducible.
    assert sum(row.predicted_elected for row in allocation) == 2


def test_allocation_is_deterministic_across_input_orderings() -> None:
    forward = [_prediction("a", 30.0), _prediction("b", 30.0)]
    reversed_order = [_prediction("b", 30.0), _prediction("a", 30.0)]

    elected_forward = {
        row.candidate_contest_id
        for row in allocate_contest(forward, seats=1)
        if row.predicted_elected
    }
    elected_reverse = {
        row.candidate_contest_id
        for row in allocate_contest(reversed_order, seats=1)
        if row.predicted_elected
    }
    assert elected_forward == elected_reverse


def test_unknown_seat_count_ranks_but_elects_nobody() -> None:
    predictions = [_prediction("a", 60.0), _prediction("b", 40.0)]
    allocation = allocate_contest(predictions, seats=None)

    assert not any(row.predicted_elected for row in allocation)
    assert all(
        row.allocation_status == "not_elected_unknown_seat_count" for row in allocation
    )
    # Ranking is still available, because it needs no cutoff.
    assert allocation[0].predicted_rank == 1


def test_allocation_refuses_a_contest_with_a_missing_prediction() -> None:
    predictions = [_prediction("a", 60.0), _prediction("b", None)]
    allocation = allocate_contest(predictions, seats=1)

    assert not any(row.predicted_elected for row in allocation)
    assert all(
        row.allocation_status == "not_allocated_missing_prediction"
        for row in allocation
    )


# --- reporting strata -----------------------------------------------------


def test_structure_strata_keep_single_and_multi_member_apart() -> None:
    features = [
        _feature("a", structure="single_member"),
        _feature("b", structure="multi_member"),
        _feature("c", structure="multi_member"),
        _feature("d", structure="multi_member", eligibility="excluded_x"),
    ]
    strata = stratify_by_structure(features)

    assert strata["single_member"] == ["a"]
    assert strata["multi_member"] == ["b", "c"]


def test_reform_census_counts_reform_and_ukip_separately() -> None:
    features = [
        _feature("a", election_id="2021", reform=True),
        _feature("b", election_id="2021", ukip=True),
        _feature("c", election_id="2021"),
        _feature("d", election_id="2026-east", reform=True),
    ]
    census = reform_census(features)

    assert census["2021"] == {"reform_uk": 1, "ukip": 1, "all_candidates": 3}
    assert census["2026-east"]["reform_uk"] == 1
    # Never summed into a shared category.
    assert census["2026-east"]["ukip"] == 0


def test_rounding_tolerance_grows_with_contest_size() -> None:
    """Matches the extractor's release-side derivation exactly."""

    assert contest_rounding_tolerance(2) == 3.0
    assert contest_rounding_tolerance(12) == 8.0
