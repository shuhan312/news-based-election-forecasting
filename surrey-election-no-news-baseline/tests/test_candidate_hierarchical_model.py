"""Tests for Architecture C: partial pooling on party effects.

The property that matters is not accuracy but the shrinkage rule: a party with
little evidence must be pulled toward the pool more than a party with a lot,
without any threshold being chosen for when a party is "too rare".
"""

import numpy as np
import pytest

from no_news_baseline.candidate_hierarchical_model import (
    DEFAULT_PARTY_PENALTY,
    PartialPoolingShareModel,
    fit_and_predict_hierarchical_fold,
    party_column_mask,
    select_hierarchical_penalties,
)
from tests.test_candidate_share_model import _rows, _targets


# --- the party block ------------------------------------------------------


def test_party_columns_are_identified_by_prefix() -> None:
    names = [
        "previous_party_vote_share",
        "standard_party_name__Conservative",
        "standard_party_name__unseen_level",
        "party_category__established",
        "incumbent_party_yes_no__yes",
    ]
    mask = party_column_mask(names)

    assert list(mask) == [False, True, True, True, False]
    # incumbent_party_yes_no is about the area's history, not party identity.
    assert mask[4] == np.False_


# --- the shrinkage rule ---------------------------------------------------


def _one_hot_design(counts: dict[str, int]) -> tuple[np.ndarray, list[str]]:
    """A design with one party indicator per party, plus one covariate."""

    names = ["covariate"] + [f"standard_party_name__{party}" for party in counts]
    rows: list[list[float]] = []
    for index, (_, count) in enumerate(counts.items()):
        for _ in range(count):
            row = [0.0] * len(names)
            row[0] = 1.0
            row[index + 1] = 1.0
            rows.append(row)
    return np.array(rows), names


def test_row_counts_survive_standardisation() -> None:
    """The regression this check exists to prevent.

    A standardised one-hot column's "off" rows sit at -mean/sd, not at zero,
    so counting non-zeros returns the whole training set and every party
    appears equally well evidenced. Counting the larger of the column's two
    values is what recovers the real figure.
    """

    design, names = _one_hot_design({"Common": 400, "Rare": 11})
    standardised = (design - design.mean(axis=0)) / np.where(
        design.std(axis=0) == 0, 1.0, design.std(axis=0)
    )
    model = PartialPoolingShareModel(fixed_penalty=1.0, party_penalty=100.0)
    model.fit(standardised, np.full(411, 2.0), party_mask=party_column_mask(names))
    shrinkage = model.shrinkage_by_party(standardised, names)

    assert shrinkage["standard_party_name__Common"]["training_rows_with_column_active"] == 400
    assert shrinkage["standard_party_name__Rare"]["training_rows_with_column_active"] == 11


def test_a_column_no_training_row_activates_carries_no_own_evidence() -> None:
    """The encoder's unseen_level column is all zeros in training. It
    contributes nothing to the fit, so its own-data weight must be zero
    rather than the whole training set."""

    design, names = _one_hot_design({"A": 20, "B": 20})
    names = names + ["standard_party_name__unseen_level"]
    design = np.hstack([design, np.zeros((design.shape[0], 1))])

    model = PartialPoolingShareModel(fixed_penalty=1.0, party_penalty=100.0)
    model.fit(design, np.full(40, 1.0), party_mask=party_column_mask(names))
    entry = model.shrinkage_by_party(design, names)["standard_party_name__unseen_level"]

    assert entry["training_rows_with_column_active"] == 0
    assert entry["own_data_weight"] == 0.0
    assert entry["pooled_weight"] == 1.0


def test_a_rare_party_is_pooled_more_than_a_common_one() -> None:
    """The whole point of Architecture C, stated as a test.

    No threshold decides that eleven observations are "too few"; the
    arithmetic n/(n + lambda) does it continuously.
    """

    design, names = _one_hot_design({"Common": 400, "Rare": 11})
    target = np.concatenate([np.full(400, 2.0), np.full(11, 2.0)])
    mask = party_column_mask(names)

    model = PartialPoolingShareModel(fixed_penalty=1.0, party_penalty=100.0)
    model.fit(design, target, party_mask=mask)
    shrinkage = model.shrinkage_by_party(design, names)

    common = shrinkage["standard_party_name__Common"]
    rare = shrinkage["standard_party_name__Rare"]

    assert common["training_rows_with_column_active"] == 400
    assert rare["training_rows_with_column_active"] == 11
    # 400/(400+100) = 0.80 against 11/(11+100) = 0.099.
    assert common["own_data_weight"] == pytest.approx(0.8)
    assert rare["own_data_weight"] == pytest.approx(11 / 111)
    assert rare["pooled_weight"] > common["pooled_weight"]


def test_a_heavier_party_penalty_pools_every_party_further() -> None:
    design, names = _one_hot_design({"A": 100, "B": 20})
    target = np.full(120, 1.0)
    mask = party_column_mask(names)

    light = PartialPoolingShareModel(fixed_penalty=1.0, party_penalty=10.0)
    light.fit(design, target, party_mask=mask)
    heavy = PartialPoolingShareModel(fixed_penalty=1.0, party_penalty=10_000.0)
    heavy.fit(design, target, party_mask=mask)

    for name in names[1:]:
        assert (
            heavy.shrinkage_by_party(design, names)[name]["own_data_weight"]
            < light.shrinkage_by_party(design, names)[name]["own_data_weight"]
        )


def test_party_and_fixed_blocks_receive_different_shrinkage() -> None:
    """The one structural difference from Architecture A."""

    rng = np.random.default_rng(0)
    design = rng.normal(size=(300, 4))
    names = ["covariate_a", "covariate_b",
             "standard_party_name__A", "standard_party_name__B"]
    target = design @ np.array([1.0, 1.0, 1.0, 1.0])
    mask = party_column_mask(names)

    model = PartialPoolingShareModel(fixed_penalty=0.1, party_penalty=10_000.0)
    model.fit(design, target, party_mask=mask)
    coefficients = model.coefficients

    # Party coefficients are crushed; covariates survive.
    assert abs(coefficients[2]) < 0.2 * abs(coefficients[0])
    assert abs(coefficients[3]) < 0.2 * abs(coefficients[1])


def test_equal_penalties_reproduce_ordinary_ridge() -> None:
    """A sanity anchor: Architecture C contains Architecture A as a case."""

    from no_news_baseline.candidate_share_model import RidgeShareModel

    rng = np.random.default_rng(1)
    design = rng.normal(size=(200, 3))
    names = ["covariate", "standard_party_name__A", "standard_party_name__B"]
    target = design @ np.array([1.5, -0.5, 0.25])

    pooled = PartialPoolingShareModel(fixed_penalty=5.0, party_penalty=5.0)
    pooled.fit(design, target, party_mask=party_column_mask(names))
    ridge = RidgeShareModel(5.0).fit(design, target)

    assert pooled.coefficients == pytest.approx(ridge.coefficients)
    assert pooled.predict(design) == pytest.approx(ridge.predict(design))


def test_negative_penalties_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        PartialPoolingShareModel(fixed_penalty=-1.0)


def test_a_mask_of_the_wrong_length_is_rejected() -> None:
    with pytest.raises(ValueError, match="one entry per column"):
        PartialPoolingShareModel().fit(
            np.zeros((5, 3)), np.zeros(5), party_mask=np.array([True, False])
        )


def test_predicting_before_fitting_raises() -> None:
    with pytest.raises(ValueError, match="must be fitted"):
        PartialPoolingShareModel().predict(np.zeros((2, 3)))


# --- joint penalty selection ---------------------------------------------


def _multi_day_training():
    shares = [40.0, 30.0, 20.0, 10.0]
    rows: list[dict] = []
    targets: dict[str, dict] = {}
    for day, prefix in (("2 May 2013", "a"), ("4 May 2017", "b"), ("6 May 2021", "c")):
        contest = _rows(day, shares, prefix)
        rows.extend(contest)
        targets.update(_targets(contest, shares))
    return rows, targets


def test_both_penalties_are_searched_together() -> None:
    train, targets = _multi_day_training()
    choice = select_hierarchical_penalties(train, targets, min_inner_rows=1)

    assert choice.method == "inner_expanding_window_validation_joint_grid"
    assert choice.inner_validation_dates == ("2017-05-04", "2021-05-06")
    # A full grid, not two separate one-dimensional searches.
    assert len(choice.grid_scores) == 25


def test_selection_falls_back_to_a_documented_default_without_inner_days() -> None:
    train, targets = _multi_day_training()
    choice = select_hierarchical_penalties(train, targets, min_inner_rows=20)

    assert choice.party_penalty == DEFAULT_PARTY_PENALTY
    assert choice.method.startswith("documented_default")
    assert choice.grid_scores == ()


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


def test_the_fold_matches_architecture_a_in_everything_but_the_penalty() -> None:
    """Predictions still sum to 100 within a contest and still allocate
    seats, so a comparison between A and C is about pooling alone."""

    train, test, targets = _fold_inputs()
    result = fit_and_predict_hierarchical_fold(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )

    assert sum(row["predicted_vote_share"] for row in result.predictions) == pytest.approx(100.0)
    assert sum(row["predicted_elected"] for row in result.predictions) == 1
    assert all(row["model_id"] == "partial_pooling_candidate_share_v1"
               for row in result.predictions)


def test_the_fold_reports_shrinkage_per_party() -> None:
    train, test, targets = _fold_inputs()
    result = fit_and_predict_hierarchical_fold(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )

    assert result.shrinkage
    for entry in result.shrinkage.values():
        assert 0.0 <= entry["own_data_weight"] <= 1.0
        assert entry["own_data_weight"] + entry["pooled_weight"] == pytest.approx(1.0)


def test_reform_rows_are_counted_for_the_fold() -> None:
    train, test, targets = _fold_inputs()
    result = fit_and_predict_hierarchical_fold(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )
    assert result.train_reform_rows == 3
    assert result.test_reform_rows == 1


def test_the_fold_is_reproducible() -> None:
    train, test, targets = _fold_inputs()
    kwargs = dict(
        split_id="s", split_role="primary_holdout",
        train_rows=train, test_rows=test, targets=targets,
    )
    first = fit_and_predict_hierarchical_fold(**kwargs)
    second = fit_and_predict_hierarchical_fold(**kwargs)
    assert [row["predicted_vote_share"] for row in first.predictions] == [
        row["predicted_vote_share"] for row in second.predictions
    ]
