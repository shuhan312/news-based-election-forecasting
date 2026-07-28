"""Tests for architecture selection.

The behaviour under test is the brief's constraint - "Do not select a complex
model based on a negligible improvement" - which is the opposite of what an
argmax over a metric column does.
"""

import pytest

from no_news_baseline.candidate_architecture_selection import (
    COMPLEXITY_ORDER,
    ArchitectureScore,
    comparison_table,
    score_architecture,
    select_architecture,
)


def _score(
    architecture: str,
    split_id: str,
    *,
    reform_mae: float,
    role: str = "development_fold",
    mae: float = 10.0,
) -> ArchitectureScore:
    return ArchitectureScore(
        architecture=architecture, split_id=split_id, split_role=role, rows=100,
        mae=mae, rmse=mae * 1.2, reform_rows=10, reform_mae=reform_mae,
        reform_rmse=reform_mae * 1.2, reform_improvement_over_equal_split=-0.1,
        winner_accuracy=0.5, seat_set_accuracy=0.4,
    )


def _full_set(a: float, c: float, b: float, *, folds: dict | None = None):
    """One decision split plus, optionally, development folds."""

    scores = [
        _score("A_regularised_linear", "holdout", reform_mae=a, role="primary_holdout"),
        _score("C_partial_pooling", "holdout", reform_mae=c, role="primary_holdout"),
        _score("B_gradient_boosted_trees", "holdout", reform_mae=b, role="primary_holdout"),
    ]
    for split_id, values in (folds or {}).items():
        for architecture, value in values.items():
            scores.append(_score(architecture, split_id, reform_mae=value))
    return scores


# --- the negligible-improvement gate --------------------------------------


def test_a_tiny_improvement_does_not_displace_the_simpler_model() -> None:
    """The brief's constraint, stated as a test: 2 per cent is not evidence."""

    outcome = select_architecture(
        _full_set(a=4.00, c=3.95, b=3.92), decision_split_id="holdout"
    )
    assert outcome.selected == "A_regularised_linear"
    assert any("does not exceed" in reason for reason in outcome.reasons)


def test_a_material_improvement_does_displace_it() -> None:
    folds = {
        "f1": {"A_regularised_linear": 5.0, "C_partial_pooling": 3.0,
               "B_gradient_boosted_trees": 3.0},
        "f2": {"A_regularised_linear": 5.0, "C_partial_pooling": 3.0,
               "B_gradient_boosted_trees": 3.0},
    }
    outcome = select_architecture(
        _full_set(a=4.00, c=3.00, b=3.00, folds=folds), decision_split_id="holdout"
    )
    assert outcome.selected == "C_partial_pooling"
    assert any("displaces" in reason for reason in outcome.reasons)


def test_the_simplest_architecture_is_the_incumbent() -> None:
    outcome = select_architecture(
        _full_set(a=4.0, c=4.0, b=4.0), decision_split_id="holdout"
    )
    assert outcome.incumbent == COMPLEXITY_ORDER[0]
    assert outcome.selected == COMPLEXITY_ORDER[0]


def test_displacement_is_sequential_so_a_winner_must_beat_the_current_holder() -> None:
    """C displaces A, then B must beat C rather than A."""

    folds = {
        "f1": {"A_regularised_linear": 9.0, "C_partial_pooling": 5.0,
               "B_gradient_boosted_trees": 5.0},
        "f2": {"A_regularised_linear": 9.0, "C_partial_pooling": 5.0,
               "B_gradient_boosted_trees": 5.0},
    }
    outcome = select_architecture(
        _full_set(a=10.0, c=5.0, b=4.9, folds=folds), decision_split_id="holdout"
    )
    assert outcome.selected == "C_partial_pooling"
    b_report = next(r for r in outcome.challenger_reports if r["challenger"] == "B_gradient_boosted_trees")
    assert b_report["incumbent"] == "C_partial_pooling"
    assert b_report["accepted"] is False


# --- the stability gate ---------------------------------------------------


def test_a_challenger_that_loses_too_many_folds_is_rejected() -> None:
    """Architecture A wins 2017 and loses the 2025 by-elections badly, so a
    single-fold comparison would select on whichever fold was looked at."""

    folds = {
        "f1": {"A_regularised_linear": 3.0, "C_partial_pooling": 5.0},
        "f2": {"A_regularised_linear": 3.0, "C_partial_pooling": 5.0},
        "f3": {"A_regularised_linear": 3.0, "C_partial_pooling": 5.0},
    }
    outcome = select_architecture(
        _full_set(a=4.0, c=2.0, b=2.0, folds=folds), decision_split_id="holdout"
    )
    # A large holdout gain, but it loses three of three development folds.
    assert outcome.selected == "A_regularised_linear"
    report = next(r for r in outcome.challenger_reports if r["challenger"] == "C_partial_pooling")
    assert report["gate_material_improvement"] is True
    assert report["gate_stability"] is False
    assert report["development_folds_lost"] == ["f1", "f2", "f3"]


def test_losing_one_fold_is_tolerated() -> None:
    folds = {
        "f1": {"A_regularised_linear": 3.0, "C_partial_pooling": 5.0},
        "f2": {"A_regularised_linear": 5.0, "C_partial_pooling": 3.0},
        "f3": {"A_regularised_linear": 5.0, "C_partial_pooling": 3.0},
    }
    outcome = select_architecture(
        _full_set(a=4.0, c=2.0, b=2.0, folds=folds), decision_split_id="holdout"
    )
    assert outcome.selected in {"C_partial_pooling", "B_gradient_boosted_trees"}


# --- guards ---------------------------------------------------------------


def test_an_incomplete_comparison_is_refused() -> None:
    """The brief requires all three architectures compared before selection."""

    scores = [
        _score("A_regularised_linear", "holdout", reform_mae=4.0, role="primary_holdout"),
        _score("C_partial_pooling", "holdout", reform_mae=3.0, role="primary_holdout"),
    ]
    with pytest.raises(ValueError, match="comparison is incomplete"):
        select_architecture(scores, decision_split_id="holdout")


def test_a_missing_decision_split_is_refused_rather_than_substituted() -> None:
    with pytest.raises(ValueError, match="no score on decision split"):
        select_architecture(_full_set(4.0, 3.0, 3.0), decision_split_id="not_run")


def test_no_scores_at_all_is_refused() -> None:
    with pytest.raises(ValueError, match="No scored architectures"):
        select_architecture([], decision_split_id="holdout")


# --- scoring and reporting ------------------------------------------------


def _prediction(row_id: str, predicted: float, observed: float, *, reform: bool = False):
    return {
        "candidate_contest_id": row_id, "election_id": "e", "division_id": "d",
        "standard_party_name": "Reform UK" if reform else "Conservative",
        "contest_structure": "single_member", "candidate_count_in_contest": 4,
        "predicted_vote_share": predicted, "observed_vote_share": observed,
        "predicted_rank": 1, "observed_rank": 1,
        "predicted_elected": True, "observed_elected": True,
        "is_reform_uk": reform, "is_ukip": False,
    }


def test_scoring_separates_reform_rows_from_the_pooled_figure() -> None:
    predictions = [
        _prediction("a", 40.0, 45.0),
        _prediction("b", 10.0, 20.0, reform=True),
    ]
    score = score_architecture(
        architecture="A_regularised_linear", split_id="holdout",
        split_role="primary_holdout", predictions=predictions,
    )
    assert score.rows == 2
    assert score.reform_rows == 1
    assert score.mae == pytest.approx(7.5)
    assert score.reform_mae == pytest.approx(10.0)


def test_comparison_table_orders_by_split_then_complexity() -> None:
    table = comparison_table(_full_set(4.0, 3.0, 2.0))
    assert [row["architecture"] for row in table] == list(COMPLEXITY_ORDER)
    assert all(row["split_id"] == "holdout" for row in table)


def test_a_challenger_with_too_few_development_folds_cannot_pass_vacuously() -> None:
    """A gate that passes when there is nothing to check is not a gate.

    Without this rule a complex architecture that was never evaluated out of
    sample would clear the stability check more easily than one that was.
    """

    outcome = select_architecture(
        _full_set(a=10.0, c=2.0, b=2.0), decision_split_id="holdout"
    )
    assert outcome.selected == "A_regularised_linear"
    report = next(
        r for r in outcome.challenger_reports if r["challenger"] == "C_partial_pooling"
    )
    assert report["gate_material_improvement"] is True
    assert report["gate_enough_folds_to_judge"] is False
    assert any("below the" in reason for reason in outcome.reasons)
