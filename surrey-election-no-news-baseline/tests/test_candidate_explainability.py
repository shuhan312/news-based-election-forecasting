"""Tests for the explainability layer."""

import numpy as np
import pytest

from no_news_baseline.candidate_explainability import (
    HIGH_SPREAD,
    INTERPRETATION_WARNING,
    SIGN_FLIP,
    FoldCoefficients,
    explain_rows,
    fit_fold_coefficients,
    party_contribution_profile,
    summarise_across_folds,
    unstable_features,
)
from no_news_baseline.candidate_features import CandidateFeatureEncoder
from no_news_baseline.candidate_share_model import RidgeShareModel, to_relative_share
from tests.test_candidate_share_model import _rows, _targets


def _fold(split_id: str, coefficients: dict[str, float]) -> FoldCoefficients:
    return FoldCoefficients(
        split_id=split_id, train_rows=100, train_reform_rows=2,
        coefficients=coefficients, intercept=1.0,
    )


# --- stability across folds ----------------------------------------------


def test_a_feature_that_changes_sign_is_flagged_unstable() -> None:
    """The core judgement: a sign flip is not a small effect, it is an effect
    whose direction the data does not determine."""

    folds = [
        _fold("f1", {"previous_party_vote_share": 0.5}),
        _fold("f2", {"previous_party_vote_share": -0.4}),
        _fold("f3", {"previous_party_vote_share": 0.3}),
    ]
    summary = summarise_across_folds(folds)
    row = next(r for r in summary if r["feature"] == "previous_party_vote_share")

    assert SIGN_FLIP in row["stability_flags"]
    assert row["stable"] is False
    assert unstable_features(summary)


def test_a_consistent_feature_is_reported_stable() -> None:
    folds = [
        _fold("f1", {"previous_party_vote_share": 0.50}),
        _fold("f2", {"previous_party_vote_share": 0.52}),
        _fold("f3", {"previous_party_vote_share": 0.48}),
    ]
    row = summarise_across_folds(folds)[0]

    assert row["stable"] is True
    assert row["stability_flags"] == []
    assert row["mean_coefficient"] == pytest.approx(0.5, abs=0.02)


def test_large_spread_is_flagged_even_without_a_sign_change() -> None:
    folds = [
        _fold("f1", {"x": 0.1}),
        _fold("f2", {"x": 3.0}),
        _fold("f3", {"x": 0.2}),
    ]
    row = summarise_across_folds(folds)[0]
    assert HIGH_SPREAD in row["stability_flags"]


def test_a_feature_absent_from_a_fold_is_recorded_absent_not_zero() -> None:
    """A party level a fold never saw must not be averaged in as zero, which
    would make a rare party look reliably unimportant."""

    folds = [
        _fold("f1", {"standard_party_name__Reform UK": 0.8, "shared": 1.0}),
        _fold("f2", {"shared": 1.0}),
    ]
    summary = {row["feature"]: row for row in summarise_across_folds(folds)}
    reform = summary["standard_party_name__Reform UK"]

    assert reform["folds_present"] == 1
    assert reform["folds_absent"] == 1
    # 0.8, not 0.4.
    assert reform["mean_coefficient"] == pytest.approx(0.8)


def test_summary_is_ranked_by_magnitude_not_signed_value() -> None:
    folds = [_fold("f1", {"small": 0.1, "large_negative": -2.0})]
    summary = summarise_across_folds(folds)
    assert summary[0]["feature"] == "large_negative"


# --- fold fitting ---------------------------------------------------------


def _training():
    shares = [40.0, 30.0, 20.0, 10.0]
    rows, targets = [], {}
    for day, prefix in (("2 May 2013", "a"), ("4 May 2017", "b"), ("6 May 2021", "c")):
        contest = _rows(day, shares, prefix)
        rows.extend(contest)
        targets.update(_targets(contest, shares))
    return rows, targets


def test_both_architectures_produce_named_coefficients() -> None:
    rows, targets = _training()
    for architecture in ("ridge", "partial_pooling"):
        fold = fit_fold_coefficients(
            split_id="s", train_rows=rows, targets=targets, architecture=architecture
        )
        assert fold.coefficients
        assert "previous_party_vote_share" in fold.coefficients
        assert fold.train_reform_rows == 3


def test_an_unknown_architecture_is_rejected() -> None:
    rows, targets = _training()
    with pytest.raises(ValueError, match="Unknown architecture"):
        fit_fold_coefficients(
            split_id="s", train_rows=rows, targets=targets, architecture="magic"
        )


# --- row contributions ----------------------------------------------------


def test_contributions_reconstruct_the_prediction_exactly() -> None:
    """A centred linear model decomposes without residue, which is why no
    approximation method is needed here."""

    rows, targets = _training()
    encoder = CandidateFeatureEncoder().fit(rows)
    design = encoder.transform(rows)
    y = to_relative_share(
        [float(targets[str(r["candidate_contest_id"])]["target_candidate_vote_share"])
         for r in rows],
        [int(r["candidate_count_in_contest"]) for r in rows],
    )
    model = RidgeShareModel(10.0).fit(design.matrix, y)
    predicted = model.predict(design.matrix)

    explanations = explain_rows(
        rows=rows, encoder=encoder, coefficients=model.coefficients,
        intercept=model.intercept, design_means=design.matrix.mean(axis=0),
        top_n=999,
    )
    reconstructed = [e.predicted_relative_share for e in explanations]

    assert reconstructed == pytest.approx(list(predicted))


def test_only_the_largest_contributions_are_returned_by_default() -> None:
    rows, targets = _training()
    encoder = CandidateFeatureEncoder().fit(rows)
    design = encoder.transform(rows)
    model = RidgeShareModel(10.0).fit(design.matrix, np.ones(len(rows)))

    explanations = explain_rows(
        rows=rows, encoder=encoder, coefficients=model.coefficients,
        intercept=model.intercept, design_means=design.matrix.mean(axis=0), top_n=5,
    )
    assert len(explanations[0].contributions) == 5
    # Ordered by magnitude.
    magnitudes = [abs(v) for _, v in explanations[0].contributions]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_every_explanation_carries_the_interpretation_warning() -> None:
    """The brief: do not present correlations as proof of causation. The
    wording travels with the numbers rather than sitting in a report."""

    rows, targets = _training()
    encoder = CandidateFeatureEncoder().fit(rows)
    design = encoder.transform(rows)
    model = RidgeShareModel(10.0).fit(design.matrix, np.ones(len(rows)))
    explanations = explain_rows(
        rows=rows, encoder=encoder, coefficients=model.coefficients,
        intercept=model.intercept, design_means=design.matrix.mean(axis=0),
    )
    assert explanations[0].interpretation_warning == INTERPRETATION_WARNING


# --- party profiles -------------------------------------------------------


def test_reform_profile_selects_only_reform_rows() -> None:
    rows, targets = _training()
    encoder = CandidateFeatureEncoder().fit(rows)
    design = encoder.transform(rows)
    model = RidgeShareModel(10.0).fit(design.matrix, np.ones(len(rows)))
    explanations = explain_rows(
        rows=rows, encoder=encoder, coefficients=model.coefficients,
        intercept=model.intercept, design_means=design.matrix.mean(axis=0),
    )

    profile = party_contribution_profile(explanations, reform_only=True)
    assert profile["rows"] == 3
    assert profile["mean_contributions"]
    assert profile["interpretation_warning"] == INTERPRETATION_WARNING


def test_an_empty_selection_returns_no_rows_rather_than_raising() -> None:
    profile = party_contribution_profile((), reform_only=True)
    assert profile["rows"] == 0
    assert profile["mean_contributions"] == []
