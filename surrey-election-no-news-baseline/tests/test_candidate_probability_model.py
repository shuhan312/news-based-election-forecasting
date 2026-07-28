"""Tests for the probability-of-election model and its scoring rules."""

import numpy as np
import pytest

from no_news_baseline.candidate_probability_model import (
    DEFAULT_PENALTY,
    LogisticElectionModel,
    brier_score,
    calibrate_to_seats,
    calibration_report,
    fit_and_predict_probability_fold,
    log_loss,
    probability_metrics,
    select_logistic_penalty,
)
from tests.test_candidate_share_model import _rows, _targets


# --- the logistic fit -----------------------------------------------------


def test_logistic_recovers_a_separable_signal() -> None:
    rng = np.random.default_rng(0)
    design = rng.normal(size=(400, 2))
    probabilities = 1.0 / (1.0 + np.exp(-(0.5 + design @ np.array([2.0, -1.0]))))
    elected = (probabilities > 0.5).astype(float)

    model = LogisticElectionModel(l2_penalty=0.01).fit(design, elected)
    predicted = model.predict_proba(design)

    assert model.converged
    assert float(np.mean((predicted > 0.5) == (elected > 0.5))) > 0.95


def test_the_intercept_is_not_penalised() -> None:
    """Shrinking it would bias every probability toward one half.

    With a rare outcome and a heavy penalty the slopes vanish, but the
    intercept must still move to the base rate.
    """

    rng = np.random.default_rng(1)
    design = rng.normal(size=(500, 3))
    elected = np.zeros(500)
    elected[:50] = 1.0  # a 10 per cent base rate

    model = LogisticElectionModel(l2_penalty=1e6).fit(design, elected)
    predicted = model.predict_proba(design)

    assert np.allclose(predicted, 0.1, atol=0.02)


def test_a_non_binary_outcome_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be binary"):
        LogisticElectionModel().fit(np.zeros((3, 2)), np.array([0.0, 0.5, 1.0]))


def test_predicting_before_fitting_raises() -> None:
    with pytest.raises(ValueError, match="must be fitted"):
        LogisticElectionModel().predict_proba(np.zeros((2, 3)))


# --- the seat constraint --------------------------------------------------


def test_probabilities_are_shifted_to_sum_to_the_seat_count() -> None:
    """The arithmetic an unconstrained logistic ignores: exactly `seats`
    candidates win."""

    raw = [0.30, 0.25, 0.20, 0.10, 0.05]
    adjusted, status = calibrate_to_seats(raw, seats=2)

    assert status == "seat_constrained"
    assert float(np.sum(adjusted)) == pytest.approx(2.0, abs=1e-8)


def test_the_constraint_preserves_the_ordering() -> None:
    """A single additive log-odds shift moves the level, not the ranking."""

    raw = [0.30, 0.25, 0.20, 0.10, 0.05]
    adjusted, _ = calibrate_to_seats(raw, seats=2)
    assert list(np.argsort(-adjusted)) == list(np.argsort(-np.array(raw)))


def test_a_single_member_contest_sums_to_one() -> None:
    adjusted, _ = calibrate_to_seats([0.1, 0.1, 0.1, 0.1], seats=1)
    assert float(np.sum(adjusted)) == pytest.approx(1.0, abs=1e-8)


def test_an_unknown_seat_count_leaves_probabilities_untouched() -> None:
    raw = [0.3, 0.2, 0.1]
    adjusted, status = calibrate_to_seats(raw, seats=None)

    assert status == "not_constrained_seats_unknown"
    assert list(adjusted) == raw


def test_an_unreachable_target_is_refused_rather_than_forced() -> None:
    # Three candidates cannot fill three seats and still be a contest.
    adjusted, status = calibrate_to_seats([0.3, 0.2, 0.1], seats=3)
    assert status == "not_constrained_target_unreachable"
    assert list(adjusted) == [0.3, 0.2, 0.1]


def test_the_constraint_works_from_a_badly_scaled_start() -> None:
    """Ten near-zero probabilities in a two-seat ward still reach 2.0."""

    adjusted, status = calibrate_to_seats([0.01] * 10, seats=2)
    assert status == "seat_constrained"
    assert float(np.sum(adjusted)) == pytest.approx(2.0, abs=1e-8)


# --- scoring rules --------------------------------------------------------


def test_brier_score_of_a_perfect_forecast_is_zero() -> None:
    assert brier_score([1.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


def test_brier_score_of_an_uninformative_half_is_a_quarter() -> None:
    assert brier_score([1.0, 0.0, 1.0, 0.0], [0.5] * 4) == pytest.approx(0.25)


def test_log_loss_clips_a_confident_miss_instead_of_returning_infinity() -> None:
    """One confident wrong call must not destroy a whole fold's metric."""

    value = log_loss([1.0, 0.0], [0.0, 1.0])
    assert np.isfinite(value)
    assert value > 10


def test_log_loss_rewards_a_confident_correct_call() -> None:
    assert log_loss([1.0, 0.0], [0.99, 0.01]) < log_loss([1.0, 0.0], [0.6, 0.4])


# --- calibration ----------------------------------------------------------


def test_a_calibrated_forecast_has_slope_near_one() -> None:
    rng = np.random.default_rng(2)
    predicted = rng.uniform(0.02, 0.98, size=4000)
    observed = (rng.uniform(size=4000) < predicted).astype(float)

    report = calibration_report(observed, predicted)

    assert report["calibration_slope"] == pytest.approx(1.0, abs=0.2)
    assert report["calibration_intercept"] == pytest.approx(0.0, abs=0.2)
    assert report["expected_calibration_error"] < 0.05


def test_an_overconfident_forecast_shows_a_slope_below_one() -> None:
    rng = np.random.default_rng(3)
    truth = rng.uniform(0.2, 0.8, size=4000)
    observed = (rng.uniform(size=4000) < truth).astype(float)
    # Push predictions toward 0 and 1: more confident than warranted.
    overconfident = np.clip((truth - 0.5) * 3.0 + 0.5, 0.01, 0.99)

    assert calibration_report(observed, overconfident)["calibration_slope"] < 0.9


def test_empty_bins_are_reported_rather_than_dropped() -> None:
    """A model that never predicts above 0.5 is itself a finding."""

    report = calibration_report([0.0, 1.0, 0.0], [0.1, 0.2, 0.1])
    assert len(report["bins"]) == 10
    assert report["bins"][-1]["rows"] == 0
    assert report["bins"][-1]["observed_frequency"] is None


# --- assembled metrics ----------------------------------------------------


def _record(row_id: str, raw: float, constrained: float, elected: bool) -> dict:
    return {
        "candidate_contest_id": row_id,
        "predicted_election_probability_raw": raw,
        "predicted_election_probability": constrained,
        "observed_elected": elected,
    }


def test_metrics_report_both_versions_and_a_base_rate_reference() -> None:
    """A Brier score is unreadable without knowing what predicting the base
    rate would have scored."""

    records = [
        _record("a", 0.6, 0.7, True),
        _record("b", 0.2, 0.15, False),
        _record("c", 0.1, 0.08, False),
        _record("d", 0.3, 0.25, False),
    ]
    metrics = probability_metrics(records)

    assert metrics["rows"] == 4
    assert metrics["observed_election_rate"] == pytest.approx(0.25)
    assert "brier_score" in metrics["seat_constrained"]
    assert "brier_score" in metrics["raw_unconstrained"]
    assert "brier_score" in metrics["base_rate_reference"]


# --- one fold -------------------------------------------------------------


def _fold_inputs():
    shares_train = [40.0, 30.0, 20.0, 10.0]
    shares_test = [50.0, 25.0, 15.0, 10.0]
    train = (
        _rows("2 May 2013", shares_train, "a")
        + _rows("4 May 2017", shares_train, "b")
        + _rows("6 May 2021", shares_train, "c")
    )
    test = _rows("7 May 2026", shares_test, "t")
    targets = {}
    for chunk, shares in (
        (train[:4], shares_train), (train[4:8], shares_train),
        (train[8:], shares_train), (test, shares_test),
    ):
        targets.update(_targets(chunk, shares))
    return train, test, targets


def test_a_fold_returns_both_raw_and_seat_constrained_probabilities() -> None:
    train, test, targets = _fold_inputs()
    result = fit_and_predict_probability_fold(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )

    assert len(result.predictions) == 4
    for row in result.predictions:
        assert 0.0 <= row["predicted_election_probability_raw"] <= 1.0
        assert 0.0 <= row["predicted_election_probability"] <= 1.0
    # One seat in this fixture, so the constrained probabilities sum to 1.
    total = sum(row["predicted_election_probability"] for row in result.predictions)
    assert total == pytest.approx(1.0, abs=1e-8)


def test_penalty_selection_uses_log_loss_not_accuracy() -> None:
    """Accuracy is nearly uninformative when most candidates lose."""

    train, _, targets = _fold_inputs()
    outcomes = {
        row_id: target["target_candidate_elected"] == "Yes"
        for row_id, target in targets.items()
    }
    choice = select_logistic_penalty(train, outcomes, min_inner_rows=1)

    assert choice.method == "inner_expanding_window_validation_log_loss"
    assert choice.inner_validation_dates == ("2017-05-04", "2021-05-06")


def test_a_fold_with_no_usable_inner_day_falls_back_to_the_default() -> None:
    train, _, targets = _fold_inputs()
    outcomes = {
        row_id: target["target_candidate_elected"] == "Yes"
        for row_id, target in targets.items()
    }
    choice = select_logistic_penalty(train, outcomes, min_inner_rows=20)

    assert choice.l2_penalty == DEFAULT_PENALTY
    assert choice.method.startswith("documented_default")


def test_the_fold_is_reproducible() -> None:
    train, test, targets = _fold_inputs()
    kwargs = dict(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )
    first = fit_and_predict_probability_fold(**kwargs)
    second = fit_and_predict_probability_fold(**kwargs)

    assert [row["predicted_election_probability"] for row in first.predictions] == [
        row["predicted_election_probability"] for row in second.predictions
    ]
