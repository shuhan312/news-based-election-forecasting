"""Tests for Architecture A: the regularised candidate-share model.

Most of these test properties rather than numbers. A ridge fit will change if
the penalty grid or the encoder changes; the guarantees that must not change
are the target scale's algebra, the order of operations in a fold, and the
rule that nothing outside a fold's training rows influences its fit.
"""

import numpy as np
import pytest

from no_news_baseline.candidate_share_model import (
    DEFAULT_PENALTY,
    PENALTY_GRID,
    RidgeShareModel,
    fit_and_predict_fold,
    select_penalty,
    to_relative_share,
    to_vote_share,
)
from tests.test_candidate_features import _row


def _rows(election_date: str, shares: list[float], prefix: str) -> list[dict]:
    """One contest whose shares sum to 100, as a real contest does.

    The party indicators are derived from the party name rather than passed
    separately, so a fixture can never claim a Reform UK candidate while
    leaving is_reform_uk False.
    """

    count = len(shares)
    return [
        {
            **_row(
                f"{prefix}{index}",
                party=party,
                election_date=election_date,
                reform=party == "Reform UK",
                ukip=party == "UK Independence Party",
            ),
            "candidate_count_in_contest": count,
            "party_count_in_contest": count,
            "analysis_number_of_seats": 1,
            "division_id": f"div-{prefix}",
        }
        for index, (party, _) in enumerate(
            zip(["Conservative", "Labour", "Liberal Democrats", "Reform UK"], shares)
        )
    ]


def _targets(rows: list[dict], shares: list[float]) -> dict[str, dict]:
    return {
        str(row["candidate_contest_id"]): {
            "target_candidate_vote_share": share,
            "target_candidate_rank": rank,
            "target_candidate_elected": "Yes" if rank == 1 else "No",
        }
        for row, share, rank in zip(
            rows, shares, np.argsort(np.argsort(-np.array(shares))) + 1
        )
    }


# --- the target scale -----------------------------------------------------


def test_relative_share_is_a_multiple_of_the_equal_split() -> None:
    # Four candidates: an equal split is 25 per cent, so 25 per cent is 1.0.
    assert to_relative_share([25.0], [4])[0] == pytest.approx(1.0)
    assert to_relative_share([50.0], [4])[0] == pytest.approx(2.0)
    # Twelve candidates: an equal split is 8.33 per cent.
    assert to_relative_share([8.3333333], [12])[0] == pytest.approx(1.0, abs=1e-6)


def test_the_scale_makes_contest_size_irrelevant_by_construction() -> None:
    """The property the transformation exists for: any complete contest has
    mean 1.0 on the relative scale, whatever its size."""

    for shares in ([60.0, 40.0], [25.0] * 4, [10.0] * 10):
        relative = to_relative_share(shares, [len(shares)] * len(shares))
        assert relative.mean() == pytest.approx(1.0)
        assert relative.sum() == pytest.approx(len(shares))


def test_the_transformation_round_trips() -> None:
    shares = [45.0, 30.0, 15.0, 10.0]
    counts = [4, 4, 4, 4]
    assert to_vote_share(to_relative_share(shares, counts), counts) == pytest.approx(
        shares
    )


def test_a_contest_with_no_candidates_is_rejected() -> None:
    with pytest.raises(ValueError, match="zero candidates"):
        to_relative_share([50.0], [0])


# --- the ridge fit --------------------------------------------------------


def test_ridge_recovers_a_clean_linear_signal_at_a_small_penalty() -> None:
    """Predictions, not the stored intercept, are what must be recovered.

    The fit is stored in a centred parameterisation, so ``intercept`` is the
    training target mean and prediction is (X - X_mean) @ w + intercept. The
    original model's value at X = 0 is therefore intercept - X_mean @ w, and
    that is what is compared here.
    """

    rng = np.random.default_rng(0)
    design = rng.normal(size=(200, 3))
    true_coefficients = np.array([1.5, -0.5, 0.0])
    target = 2.0 + design @ true_coefficients

    model = RidgeShareModel(l2_penalty=0.001).fit(design, target)

    assert model.coefficients == pytest.approx(true_coefficients, abs=0.05)
    assert model.predict(design) == pytest.approx(target, abs=0.05)
    implied_value_at_zero = model.intercept - design.mean(axis=0) @ model.coefficients
    assert implied_value_at_zero == pytest.approx(2.0, abs=0.05)


def test_a_larger_penalty_shrinks_coefficients_but_not_the_intercept() -> None:
    """Penalising the intercept would pull every prediction toward zero."""

    rng = np.random.default_rng(1)
    design = rng.normal(size=(100, 3))
    target = 5.0 + design @ np.array([2.0, 2.0, 2.0])

    light = RidgeShareModel(0.1).fit(design, target)
    heavy = RidgeShareModel(1000.0).fit(design, target)

    assert np.all(np.abs(heavy.coefficients) < np.abs(light.coefficients))
    # The intercept is the training mean either way.
    assert heavy.intercept == pytest.approx(light.intercept)


def test_a_negative_penalty_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        RidgeShareModel(-1.0)


def test_predicting_before_fitting_raises() -> None:
    with pytest.raises(ValueError, match="must be fitted"):
        RidgeShareModel().predict(np.zeros((2, 3)))


# --- penalty selection ----------------------------------------------------


def _multi_day_training() -> tuple[list[dict], dict[str, dict]]:
    """Three polling days of training rows, so inner folds are possible."""

    shares = [40.0, 30.0, 20.0, 10.0]
    rows: list[dict] = []
    targets: dict[str, dict] = {}
    for day, prefix in (("2 May 2013", "a"), ("4 May 2017", "b"), ("6 May 2021", "c")):
        contest = _rows(day, shares, prefix)
        rows.extend(contest)
        targets.update(_targets(contest, shares))
    return rows, targets


def test_penalty_is_selected_inside_the_training_rows() -> None:
    train, targets = _multi_day_training()
    # These fixture contests are far below the production minimum, so the
    # threshold is lowered explicitly here to exercise the mechanism.
    choice = select_penalty(train, targets, min_inner_rows=1)

    assert choice.method == "inner_expanding_window_validation"
    # The first polling day has nothing earlier and cannot be an inner test.
    assert choice.inner_validation_dates == ("2017-05-04", "2021-05-06")
    assert choice.l2_penalty in PENALTY_GRID
    assert len(choice.grid_scores) == len(PENALTY_GRID)


def test_inner_validation_averages_over_several_days_not_just_the_last() -> None:
    """One small unusual election must not decide the penalty alone."""

    train, targets = _multi_day_training()
    choice = select_penalty(train, targets, min_inner_rows=1, max_inner_folds=3)
    assert len(choice.inner_validation_dates) == 2


def test_a_too_small_inner_day_is_skipped_rather_than_scored() -> None:
    """The guard that a three-row by-election cannot choose the penalty.

    Selecting on such a day chose the heaviest penalty in the grid and nearly
    doubled outer test error in the fold that trains through 2020.
    """

    train, targets = _multi_day_training()
    choice = select_penalty(train, targets, min_inner_rows=20)

    assert choice.inner_validation_dates == ()
    assert choice.l2_penalty == DEFAULT_PENALTY
    assert choice.method == "documented_default_no_inner_validation_day_large_enough"
    assert choice.grid_scores == ()


def test_a_single_training_polling_day_falls_back_to_a_documented_default() -> None:
    """No inner split exists, so the penalty is declared, not chosen."""

    shares = [40.0, 30.0, 20.0, 10.0]
    train = _rows("6 May 2021", shares, "a")
    choice = select_penalty(train, _targets(train, shares), min_inner_rows=1)

    assert choice.l2_penalty == DEFAULT_PENALTY
    assert choice.method.startswith("documented_default")
    assert choice.grid_scores == ()


def test_a_penalty_at_the_grid_edge_is_flagged_not_silently_accepted() -> None:
    """A boundary hit means the grid bounded the search, not the data."""

    train, targets = _multi_day_training()
    narrow = select_penalty(train, targets, min_inner_rows=1, grid=(1.0, 2.0))
    assert narrow.hit_grid_boundary is True


# --- one fold end to end --------------------------------------------------


def _fold_inputs():
    shares_train = [40.0, 30.0, 20.0, 10.0]
    shares_test = [50.0, 25.0, 15.0, 10.0]
    train = _rows("4 May 2017", shares_train, "a") + _rows(
        "6 May 2021", shares_train, "b"
    )
    test = _rows("7 May 2026", shares_test, "t")
    targets = {
        **_targets(train[:4], shares_train),
        **_targets(train[4:], shares_train),
        **_targets(test, shares_test),
    }
    return train, test, targets


def test_predicted_shares_sum_to_one_hundred_within_a_contest() -> None:
    train, test, targets = _fold_inputs()
    result = fit_and_predict_fold(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )
    total = sum(row["predicted_vote_share"] for row in result.predictions)

    assert total == pytest.approx(100.0)
    assert all(row["normalisation_status"] == "normalised" for row in result.predictions)


def test_both_scales_are_retained_in_every_record() -> None:
    """A fault must not be able to hide behind the transformation."""

    train, test, targets = _fold_inputs()
    result = fit_and_predict_fold(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )
    row = result.predictions[0]

    assert row["predicted_relative_share"] is not None
    assert row["predicted_vote_share_unnormalised"] is not None
    assert row["predicted_vote_share"] is not None


def test_seat_allocation_uses_the_known_pre_election_seat_count() -> None:
    train, test, targets = _fold_inputs()
    result = fit_and_predict_fold(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )
    elected = [row for row in result.predictions if row["predicted_elected"]]

    # One seat in this fixture, so exactly one predicted winner.
    assert len(elected) == 1
    assert elected[0]["predicted_rank"] == 1


def test_records_carry_the_observed_outcome_for_scoring() -> None:
    train, test, targets = _fold_inputs()
    result = fit_and_predict_fold(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )
    for row in result.predictions:
        assert row["observed_vote_share"] is not None
        assert row["absolute_error"] == pytest.approx(
            abs(row["predicted_vote_share"] - row["observed_vote_share"])
        )


def test_reform_rows_are_counted_for_the_fold() -> None:
    """The brief requires the Reform sample size of every fold to be reported."""

    train, test, targets = _fold_inputs()
    result = fit_and_predict_fold(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )
    assert result.train_reform_rows == 2  # one per training contest
    assert result.test_reform_rows == 1


def test_an_empty_training_or_test_fold_raises_rather_than_scoring_nothing() -> None:
    train, test, targets = _fold_inputs()
    with pytest.raises(ValueError, match="no training rows"):
        fit_and_predict_fold(
            split_id="s", split_role="r", train_rows=[], test_rows=test, targets=targets
        )
    with pytest.raises(ValueError, match="no test rows"):
        fit_and_predict_fold(
            split_id="s", split_role="r", train_rows=train, test_rows=[], targets=targets
        )


def test_the_fold_is_reproducible() -> None:
    """Closed-form ridge and a deterministic encoder mean no seed is needed;
    two runs of the same fold must be identical to the last decimal."""

    train, test, targets = _fold_inputs()
    kwargs = dict(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )
    first = fit_and_predict_fold(**kwargs)
    second = fit_and_predict_fold(**kwargs)

    assert [row["predicted_vote_share"] for row in first.predictions] == [
        row["predicted_vote_share"] for row in second.predictions
    ]
