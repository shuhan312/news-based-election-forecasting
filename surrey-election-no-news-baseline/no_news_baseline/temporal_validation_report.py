"""Score the existing parameter-free benchmarks fold-by-fold, over time.

Purpose
-------
``temporal_validation.py`` only builds the train/test split; it makes no
prediction and reports no accuracy. This module is the first thing to
actually run predictions through that split, using the three benchmarks
already built (``previous_result_persistence_v1``, ``equal_share_reference_
v1``, ``party_historical_mean_reference_v1``) rather than a new fitted
model. It plays the same role as Hanretty (2021, Section 5.3, "Forecasting
ten elections ahead" / Figure 3): track accuracy election-by-election as the
amount of available history grows, to see whether prediction difficulty is
roughly constant or drifts over the period studied.

Because these three benchmarks have no fitted parameters, this is also a
real-data extension of the cross-check already exercised in
``test_temporal_validation.py``: scoring each fold's own test rows in
isolation must reproduce exactly the numbers the whole-dataset benchmark
functions already report for that election. Any mismatch here would mean
the fold boundaries disagree with the benchmarks' own election grouping, and
should be treated as a bug in this module rather than in the benchmarks.

This module does not fit anything and does not choose a "winning" benchmark;
it only reports the same three already-defined rules against the same folds
that a future fitted model in ``regularised_models.py`` will have to use.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from no_news_baseline.benchmark_metrics import share_metrics_for_predictions
from no_news_baseline.naive_benchmarks import (
    evaluate_equal_share_reference,
    evaluate_party_historical_mean_reference,
)
from no_news_baseline.persistence_benchmark import evaluate_previous_result_persistence
from no_news_baseline.temporal_validation import TemporalFold, iter_temporal_folds


# Every benchmark in this project returns the same
# ``(predictions, metrics, audit)`` shape, so the report loop below can treat
# all three identically instead of special-casing each one.
_BENCHMARKS = (
    ("previous_result_persistence_v1", evaluate_previous_result_persistence),
    ("equal_share_reference_v1", evaluate_equal_share_reference),
    ("party_historical_mean_reference_v1", evaluate_party_historical_mean_reference),
)


def score_benchmarks_across_folds(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Return one row per fold, with each benchmark's share MAE on that fold.

    Each benchmark is re-run on exactly that fold's own rows (its training
    rows plus its one held-out election), not on the whole release. This
    keeps the report honest about what a benchmark could have known at that
    point in time, even though these particular benchmarks do not use their
    training rows for anything beyond what each row already carries.
    """

    folds = iter_temporal_folds(features, targets)
    return tuple(_score_one_fold(fold) for fold in folds)


def _score_one_fold(fold: TemporalFold) -> dict[str, object]:
    fold_features = fold.train_features + fold.test_features
    fold_targets = fold.train_targets + fold.test_targets
    test_ids = {str(row["party_contest_id"]) for row in fold.test_features}

    row: dict[str, object] = {
        "election_id": fold.election_id,
        "election_date": fold.election_date.date().isoformat(),
        "election_year": fold.election_year,
        "election_type": fold.election_type,
        "train_rows": len(fold.train_features),
        "test_rows": len(fold.test_features),
    }
    for benchmark_id, evaluate in _BENCHMARKS:
        predictions, _metrics, _audit = evaluate(fold_features, fold_targets)
        # Every benchmark predicts for its own eligible rows, which may
        # include some training-election rows too (e.g. equal_share_
        # reference predicts for every single-member row it is given); only
        # this fold's held-out election counts as a genuine "next election"
        # test result.
        test_predictions = [
            prediction
            for prediction in predictions
            if str(prediction["party_contest_id"]) in test_ids
        ]
        row[benchmark_id] = share_metrics_for_predictions(test_predictions)
    return row
