"""Compare every no-news model on one identical, shared set of contests.

Purpose
-------
The project now has four no-news predictors of single-member party vote
share: three parameter-free benchmarks (``previous_result_persistence_v1``,
``equal_share_reference_v1``, ``party_historical_mean_reference_v1``) and one
fitted model (``ridge_fundamentals_v1``). The supervisor's headline question -
does news add value over previous results - can only be answered if these are
first ranked honestly against each other, and a fitted model must never look
better simply because it was scored on an easier or smaller set of rows
(``docs/persistence_benchmark.md``, "Interpretation boundary").

This module enforces that discipline. The ridge model is evaluated
fold-wise, so it can only score contests in elections that have earlier
training data; it therefore scores fewer rows than a whole-dataset benchmark
run. Rather than compare across different row sets, this module intersects
the contests every model actually predicted and scores all four on exactly
that shared set, using the single shared ``benchmark_metrics`` implementation.

Why restricting whole-dataset benchmark predictions to the shared set is
legitimate: the three benchmarks are parameter-free, so a benchmark's
prediction for a given contest is identical whether it was produced in a
whole-dataset run or a fold-wise run (proved in
``test_temporal_validation.py`` and ``test_temporal_validation_report.py``).
Filtering their whole-dataset predictions down to the ridge-scored contests
therefore yields exactly the numbers a fold-wise run would have produced,
without re-deriving them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from no_news_baseline.benchmark_metrics import share_metrics_for_predictions
from no_news_baseline.naive_benchmarks import (
    evaluate_equal_share_reference,
    evaluate_party_historical_mean_reference,
)
from no_news_baseline.persistence_benchmark import evaluate_previous_result_persistence
from no_news_baseline.regularised_models import evaluate_ridge_over_folds


def compare_models_on_common_support(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
    l2_penalty: float = 1.0,
) -> dict[str, object]:
    """Score every no-news model on the contests all of them predicted.

    Returns the shared-contest count and, per model, the share-error metrics
    on exactly those contests. A model is only comparable on rows it actually
    produced a numeric share prediction for, so the shared set is the
    intersection of every model's own predicted contests; reporting that count
    makes the comparison's scope explicit rather than implied.
    """

    feature_rows = list(features)
    target_rows = list(targets)

    # The fitted model is the narrowest: it only scores fold test rows with
    # training data, so its contest set defines the ceiling of what can be
    # compared. Every benchmark is then cut down to meet it.
    ridge_predictions = evaluate_ridge_over_folds(feature_rows, target_rows, l2_penalty)
    persistence_predictions, _pm, _pa = evaluate_previous_result_persistence(
        feature_rows, target_rows
    )
    equal_share_predictions, _em, _ea = evaluate_equal_share_reference(
        feature_rows, target_rows
    )
    party_mean_predictions, _cm, _ca = evaluate_party_historical_mean_reference(
        feature_rows, target_rows
    )

    predictions_by_model = {
        "ridge_fundamentals_v1": ridge_predictions,
        "previous_result_persistence_v1": persistence_predictions,
        "equal_share_reference_v1": equal_share_predictions,
        "party_historical_mean_reference_v1": party_mean_predictions,
    }

    # A contest counts as shared only if every model produced a numeric share
    # prediction for it. Building the intersection this way means no model is
    # ever scored on a row another model could not predict.
    scored_ids_by_model = {
        model_id: {
            str(row["party_contest_id"])
            for row in rows
            if row["predicted_party_vote_share"] is not None
        }
        for model_id, rows in predictions_by_model.items()
    }
    shared_ids = set.intersection(*scored_ids_by_model.values())

    model_metrics = {
        model_id: share_metrics_for_predictions(
            [
                row
                for row in rows
                if str(row["party_contest_id"]) in shared_ids
                and row["predicted_party_vote_share"] is not None
            ]
        )
        for model_id, rows in predictions_by_model.items()
    }

    return {
        "l2_penalty": l2_penalty,
        "shared_contest_count": len(shared_ids),
        "per_model_scored_contest_counts": {
            model_id: len(ids) for model_id, ids in scored_ids_by_model.items()
        },
        "common_support_share_metrics": model_metrics,
        "comparison_note": (
            "All models scored on the identical set of single-member contests that every "
            "model predicted, using one shared metric implementation. A fitted model does "
            "not appear stronger by being scored on fewer or easier contests."
        ),
    }
