"""Task 3: join the coverage-evaluation universe to the N0-N3 predictions.

Purpose
-------
``coverage_evaluation.py`` (Task 2) answers "why can't this row be
predicted" for every row in the release. This module answers the
complementary empirical question: given that account, what did each model
actually do? It joins the declared universe against each model's real
prediction output and classifies every (row, model) pair into exactly one
outcome - predicted, eligible-but-unpredicted, ineligible-but-predicted
(a integrity violation), or not eligible - rather than only reporting
accuracy on whichever rows happened to have a prediction.

Two distinct coverage denominators are reported deliberately, because they
answer different questions and must not be conflated (this is itself one
of the points the methodology documentation must explain):

- ``target_universe_coverage`` = valid predictions / ALL rows in the
  universe (or in the cohort). This says how much of the whole electoral
  landscape a model actually speaks to.
- ``eligibility_conditioned_coverage`` = valid predictions / rows the model
  is theoretically ELIGIBLE to predict. This says how completely a model
  exploits the information it is, in principle, entitled to use - a value
  below 100% here means the model is silently failing on rows its own
  design says it should be able to handle, which is a genuine coverage gap
  rather than a structural limit.

Join integrity
---------------
Every one of the four ``evaluate_*`` functions already asserts internally
that its own predictions contain no duplicate ``party_contest_id`` (see
each module's own ``_assert_..._well_formed``/``_assert_prediction_
integrity``). The checks in this module are therefore a second,
independent line of defence: they must never trigger against the real
benchmark code, but they are exercised directly with hand-built,
deliberately broken prediction lists in the test suite, so this join layer
does not simply assume upstream correctness.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from no_news_baseline.benchmark_metrics import share_metrics_for_predictions
from no_news_baseline.coverage_evaluation import build_evaluation_universe
from no_news_baseline.model_comparison import compare_models_on_common_support
from no_news_baseline.naive_benchmarks import (
    evaluate_equal_share_reference,
    evaluate_party_historical_mean_reference,
)
from no_news_baseline.persistence_benchmark import evaluate_previous_result_persistence
from no_news_baseline.regularised_models import evaluate_ridge_over_folds


N0 = "equal_share_reference_v1"
N1 = "party_historical_mean_reference_v1"
N2 = "previous_result_persistence_v1"
N3 = "ridge_fundamentals_v1"
MODEL_IDS = (N0, N1, N2, N3)

# Each model's theoretical eligibility is read from the column
# coverage_evaluation.py already computed by calling that model's own
# cohort predicate. No eligibility rule is redefined here.
ELIGIBILITY_FIELD_BY_MODEL = {
    N0: "eligible_n0_equal_share",
    N1: "eligible_n1_party_historical_mean",
    N2: "eligible_n2_persistence_share",
    N3: "eligible_n3_ridge",
}

# Controlled vocabulary for the per-row-per-model join outcome.
REASON_NOT_ELIGIBLE = "not_theoretically_eligible"
REASON_INELIGIBLE_BUT_PREDICTED = "prediction_for_ineligible_row"
REASON_ELIGIBLE_MISSING_PREDICTION = "eligible_row_missing_prediction"
REASON_ELIGIBLE_PREDICTED_NO_VALUE = "eligible_predicted_but_value_unavailable"
REASON_ELIGIBLE_AND_PREDICTED = "eligible_and_predicted"


def run_all_models_and_build_coverage_table(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
    l2_penalty: float = 1.0,
) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
    """Convenience wrapper: run the real N0-N3 models, then join and classify."""

    feature_rows = list(features)
    target_rows = list(targets)
    universe = build_evaluation_universe(feature_rows, target_rows)

    n0_predictions, _m0, _a0 = evaluate_equal_share_reference(feature_rows, target_rows)
    n1_predictions, _m1, _a1 = evaluate_party_historical_mean_reference(
        feature_rows, target_rows
    )
    n2_predictions, _m2, _a2 = evaluate_previous_result_persistence(feature_rows, target_rows)
    # Ridge's evaluator returns predictions only (no metrics/audit dict),
    # unlike the other three, because it is fold-wise rather than a single
    # whole-dataset pass; the difference is real and is not papered over.
    n3_predictions = evaluate_ridge_over_folds(feature_rows, target_rows, l2_penalty)

    predictions_by_model = {
        N0: n0_predictions,
        N1: n1_predictions,
        N2: n2_predictions,
        N3: n3_predictions,
    }
    return build_prediction_coverage_table(universe, predictions_by_model)


def build_prediction_coverage_table(
    universe: Sequence[Mapping[str, object]],
    predictions_by_model: Mapping[str, Sequence[Mapping[str, object]]],
) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
    """Join a pre-built universe to already-computed model predictions.

    Kept separate from ``run_all_models_and_build_coverage_table`` so the
    join and classification logic can be tested directly against small,
    deliberately malformed prediction lists, without needing the real
    benchmarks (which already refuse to produce malformed output) to be
    coerced into an invalid state.
    """

    universe_by_id = {str(row["party_contest_id"]): row for row in universe}
    if len(universe_by_id) != len(universe):
        raise ValueError("Evaluation universe contains a duplicate party_contest_id.")

    prediction_index_by_model: dict[str, dict[str, Mapping[str, object]]] = {}
    mismatches: list[dict[str, object]] = []
    for model_id in MODEL_IDS:
        predictions = predictions_by_model.get(model_id, ())
        index, model_mismatches = _index_predictions(model_id, predictions, universe_by_id)
        prediction_index_by_model[model_id] = index
        mismatches.extend(model_mismatches)

    rows: list[dict[str, object]] = []
    for party_contest_id, universe_row in universe_by_id.items():
        for model_id in MODEL_IDS:
            rows.append(
                _classify_one_row(
                    model_id=model_id,
                    universe_row=universe_row,
                    prediction=prediction_index_by_model[model_id].get(party_contest_id),
                )
            )
        mismatches.extend(
            _ineligible_but_predicted_mismatches(
                party_contest_id, universe_row, prediction_index_by_model
            )
        )

    join_report = {
        "universe_row_count": len(universe_by_id),
        "join_row_count": len(rows),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }
    return tuple(rows), join_report


def _index_predictions(
    model_id: str,
    predictions: Sequence[Mapping[str, object]],
    universe_by_id: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, Mapping[str, object]], list[dict[str, object]]]:
    """Index one model's predictions by ID, reporting duplicates and orphans.

    A duplicate or an orphaned prediction (referencing a party_contest_id the
    universe does not contain) is recorded, not silently ignored - the first
    occurrence is kept in the index so downstream classification can still
    proceed, but the anomaly itself is never lost.
    """

    index: dict[str, Mapping[str, object]] = {}
    mismatches: list[dict[str, object]] = []
    for prediction in predictions:
        contest_id = str(prediction["party_contest_id"])
        if contest_id in index:
            mismatches.append(
                {
                    "mismatch_type": "duplicate_prediction",
                    "model_id": model_id,
                    "party_contest_id": contest_id,
                }
            )
            continue
        if contest_id not in universe_by_id:
            mismatches.append(
                {
                    "mismatch_type": "prediction_without_target",
                    "model_id": model_id,
                    "party_contest_id": contest_id,
                }
            )
            continue
        index[contest_id] = prediction
    return index, mismatches


def _classify_one_row(
    *,
    model_id: str,
    universe_row: Mapping[str, object],
    prediction: Mapping[str, object] | None,
) -> dict[str, object]:
    eligible = bool(universe_row[ELIGIBILITY_FIELD_BY_MODEL[model_id]])
    present = prediction is not None
    predicted_value = prediction.get("predicted_party_vote_share") if present else None
    valid = predicted_value is not None
    actual_value = universe_row.get("actual_party_vote_share")
    has_actual = isinstance(actual_value, (int, float))

    # An "ineligible but predicted" violation must be judged on whether the
    # model claimed an actual SHARE VALUE (``valid``), not merely on whether
    # an entry exists (``present``). persistence_benchmark legitimately keeps
    # a row present with predicted_party_vote_share=None for a party that is
    # winner-cohort-eligible but not share-cohort-eligible (see
    # docs/coverage_aware_evaluation_methodology.md); that is correct
    # behaviour, not a share-eligibility violation, and must not be flagged
    # as one.
    if not eligible and not valid:
        reason = REASON_NOT_ELIGIBLE
    elif not eligible and valid:
        reason = REASON_INELIGIBLE_BUT_PREDICTED
    elif eligible and not present:
        reason = REASON_ELIGIBLE_MISSING_PREDICTION
    elif eligible and present and not valid:
        reason = REASON_ELIGIBLE_PREDICTED_NO_VALUE
    else:
        reason = REASON_ELIGIBLE_AND_PREDICTED

    share_error = (
        float(predicted_value) - float(actual_value)
        if valid and has_actual
        else None
    )
    return {
        "party_contest_id": universe_row["party_contest_id"],
        "model_id": model_id,
        "primary_cohort": universe_row["primary_cohort"],
        "election_id": universe_row["election_id"],
        "election_type": universe_row["election_type"],
        "theoretically_eligible": eligible,
        "prediction_present": present,
        "prediction_valid": valid,
        "actual_party_vote_share": actual_value if has_actual else None,
        "predicted_party_vote_share": predicted_value,
        "share_error": share_error,
        "absolute_share_error": abs(share_error) if share_error is not None else None,
        "squared_share_error": share_error**2 if share_error is not None else None,
        "reason": reason,
    }


def _ineligible_but_predicted_mismatches(
    party_contest_id: str,
    universe_row: Mapping[str, object],
    prediction_index_by_model: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for model_id in MODEL_IDS:
        eligible = bool(universe_row[ELIGIBILITY_FIELD_BY_MODEL[model_id]])
        predicted = prediction_index_by_model[model_id].get(party_contest_id)
        # As in _classify_one_row: only an actual claimed share value counts
        # as a violation. A present-but-null entry (e.g. persistence tracking
        # a winner-only row) is not a share-eligibility violation.
        claimed_value = predicted is not None and predicted.get("predicted_party_vote_share") is not None
        if not eligible and claimed_value:
            found.append(
                {
                    "mismatch_type": "prediction_for_ineligible_row",
                    "model_id": model_id,
                    "party_contest_id": party_contest_id,
                }
            )
    return found


def summarise_coverage(
    coverage_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Per model, overall and by cohort: counts, both coverage rates, MAE."""

    by_model: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in coverage_rows:
        by_model[str(row["model_id"])].append(row)

    return {
        model_id: {
            "overall": _cohort_summary(rows),
            "by_cohort": {
                cohort: _cohort_summary(
                    [row for row in rows if row["primary_cohort"] == cohort]
                )
                for cohort in sorted({row["primary_cohort"] for row in rows})
            },
        }
        for model_id, rows in by_model.items()
    }


def _cohort_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    target_count = len(rows)
    eligible_count = sum(row["theoretically_eligible"] for row in rows)
    valid_count = sum(row["prediction_valid"] for row in rows)
    valid_rows = [row for row in rows if row["prediction_valid"]]
    return {
        "target_count": target_count,
        "theoretically_eligible_count": eligible_count,
        "valid_prediction_count": valid_count,
        "target_universe_coverage": (
            valid_count / target_count if target_count else None
        ),
        "eligibility_conditioned_coverage": (
            valid_count / eligible_count if eligible_count else None
        ),
        "own_covered_sample_mae": share_metrics_for_predictions(valid_rows)[
            "party_share_mae_percentage_points"
        ],
    }


def common_sample_metrics(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
    l2_penalty: float = 1.0,
) -> dict[str, object]:
    """Common-sample MAE across all four models, on identical target IDs.

    Delegates to ``model_comparison.compare_models_on_common_support``,
    which already builds the exact-intersection common sample this task
    requires; this function is not a second, independently written
    implementation of that intersection logic.
    """

    return compare_models_on_common_support(features, targets, l2_penalty)


def winner_coverage_metrics(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Winner coverage/accuracy for the two models that predict winners.

    "Complete area-level party prediction sets" means every party contesting
    an area received a definite Yes/No from that model, never a partial
    area where only some parties were resolved. Both
    ``previous_result_persistence_v1`` and ``party_historical_mean_
    reference_v1`` already enforce this at the row level via their own
    ``winner_prediction_status`` field (set once per area, not per party);
    this function reads that existing field rather than re-deriving
    area-completeness.
    """

    feature_rows = list(features)
    target_rows = list(targets)
    persistence_predictions, _m, _a = evaluate_previous_result_persistence(
        feature_rows, target_rows
    )
    climatology_predictions, _m2, _a2 = evaluate_party_historical_mean_reference(
        feature_rows, target_rows
    )

    return {
        N2: _winner_metrics_for(persistence_predictions),
        N1: _winner_metrics_for(climatology_predictions),
        N0: {
            "available": False,
            "reason": "equal_share_reference_v1 predicts an identical share for every "
            "party on the ballot and therefore has no basis to single out a winner.",
        },
        N3: {
            "available": False,
            "reason": "ridge_fundamentals_v1 is a share regression only; no winner "
            "classification rule is defined for it in this task.",
        },
    }


def _winner_metrics_for(predictions: Sequence[Mapping[str, object]]) -> dict[str, object]:
    by_area: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in predictions:
        by_area[(str(row["election_id"]), str(row["division_id"]))].append(row)

    eligible_areas = len(by_area)
    predicted_areas = [
        area_rows
        for area_rows in by_area.values()
        if all(row["predicted_party_elected"] != "Unknown" for row in area_rows)
    ]
    correct = sum(
        any(
            row["predicted_party_elected"] == "Yes" == row["actual_party_elected"]
            for row in area_rows
        )
        for area_rows in predicted_areas
    )
    predicted_count = len(predicted_areas)
    return {
        "available": True,
        "winner_eligible_area_count": eligible_areas,
        "winner_predicted_area_count": predicted_count,
        "winner_coverage": predicted_count / eligible_areas if eligible_areas else None,
        "winner_accuracy": correct / predicted_count if predicted_count else None,
    }
