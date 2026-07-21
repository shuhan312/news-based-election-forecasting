"""Shared scoring logic for every no-news benchmark.

Why this module exists
-----------------------
``persistence_benchmark.py`` originally computed its own MAE/RMSE/binary
metrics privately. As soon as a second parameter-free benchmark
(``naive_benchmarks.py``) needed to be scored on the *same* declared cohort
(see ``docs/persistence_benchmark.md``, "Interpretation boundary"), keeping two
independent metric implementations would risk them silently drifting apart -
for example one rounding a percentage and the other not. A methods comparison
between benchmarks is only valid if every benchmark is scored by literally the
same code, so this module is the single place that defines "error", "MAE",
"accuracy" etc. for the whole project. Every benchmark module should import
from here rather than redefine these functions.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from math import sqrt
from statistics import median


def assert_one_to_one_party_contest_release(
    features: list[Mapping[str, object]], targets: list[Mapping[str, object]]
) -> dict[str, Mapping[str, object]]:
    """Fail fast on a malformed release; return targets indexed by contest id.

    The extractor publishes features and targets as two separate JSON files
    (see ``docs/data_contract.md``). Every benchmark needs the same check
    before scoring, because a duplicated or mismatched ``party_contest_id``
    would silently attach one party's history to a different party's outcome.
    """

    feature_ids = [str(row["party_contest_id"]) for row in features]
    target_ids = [str(row["party_contest_id"]) for row in targets]
    if len(feature_ids) != len(set(feature_ids)) or len(target_ids) != len(set(target_ids)):
        raise ValueError("Party-contest release contains duplicate identifiers.")
    if set(feature_ids) != set(target_ids):
        raise ValueError("Feature and target party-contest identifiers do not match.")
    return {str(row["party_contest_id"]): row for row in targets}


def share_metrics_for_predictions(rows: list[Mapping[str, object]]) -> dict[str, object]:
    """Summarise party vote-share error for rows carrying a scored prediction.

    A row is only included if ``predicted_party_vote_share`` is not ``None``.
    Benchmarks decide their own eligibility rules upstream; this function only
    aggregates whatever it is given.
    """

    share_rows = [row for row in rows if row["predicted_party_vote_share"] is not None]
    absolute_errors = [float(row["absolute_share_error"]) for row in share_rows]
    squared_errors = [float(row["squared_share_error"]) for row in share_rows]
    signed_errors = [float(row["share_error"]) for row in share_rows]
    return {
        "party_share_rows": len(share_rows),
        "party_share_mae_percentage_points": (
            sum(absolute_errors) / len(absolute_errors) if absolute_errors else None
        ),
        "party_share_rmse_percentage_points": (
            sqrt(sum(squared_errors) / len(squared_errors)) if squared_errors else None
        ),
        "party_share_median_absolute_error_percentage_points": (
            median(absolute_errors) if absolute_errors else None
        ),
        "party_share_mean_error_percentage_points": (
            sum(signed_errors) / len(signed_errors) if signed_errors else None
        ),
    }


def winner_metrics_for_predictions(rows: list[Mapping[str, object]]) -> dict[str, object]:
    """Summarise winner classification quality for a set of party rows.

    Rows whose ``predicted_party_elected`` is ``"Unknown"`` are counted as
    unscored rather than being coerced into a guess, matching the project rule
    that an unavailable prediction must stay visible, never silently dropped
    or defaulted to "No".
    """

    winner_rows = [row for row in rows if row["predicted_party_elected"] != "Unknown"]
    result: dict[str, object] = {
        "winner_party_rows_scored": len(winner_rows),
        "winner_party_rows_unscored": len(rows) - len(winner_rows),
    }
    result.update(binary_classification_metrics(winner_rows))
    result.update(area_winner_accuracy(winner_rows))
    return result


def binary_classification_metrics(rows: list[Mapping[str, object]]) -> dict[str, object]:
    """Row-level Yes/No classification metrics for a "did this party win" call."""

    if not rows:
        return {
            "winner_party_row_accuracy": None,
            "winner_party_balanced_accuracy": None,
            "winner_party_macro_f1": None,
            "winner_party_hard_brier_score": None,
        }
    actual = [row["actual_party_elected"] == "Yes" for row in rows]
    predicted = [row["predicted_party_elected"] == "Yes" for row in rows]
    tp = sum(a and p for a, p in zip(actual, predicted, strict=True))
    tn = sum(not a and not p for a, p in zip(actual, predicted, strict=True))
    fp = sum(not a and p for a, p in zip(actual, predicted, strict=True))
    fn = sum(a and not p for a, p in zip(actual, predicted, strict=True))
    sensitivity = _safe_ratio(tp, tp + fn)
    specificity = _safe_ratio(tn, tn + fp)
    f1_yes = _f1(tp, fp, fn)
    f1_no = _f1(tn, fn, fp)
    return {
        "winner_party_row_accuracy": (tp + tn) / len(rows),
        "winner_party_balanced_accuracy": (
            (sensitivity + specificity) / 2
            if sensitivity is not None and specificity is not None
            else None
        ),
        "winner_party_macro_f1": (
            (f1_yes + f1_no) / 2 if f1_yes is not None and f1_no is not None else None
        ),
        # Every naive/persistence rule in this project emits a deterministic
        # Yes/No decision, never a calibrated probability. This Brier score is
        # therefore labelled "hard" so it is never mistaken for probabilistic
        # calibration when a genuinely probabilistic model is added later.
        "winner_party_hard_brier_score": (fp + fn) / len(rows),
        "winner_party_confusion_tp": tp,
        "winner_party_confusion_tn": tn,
        "winner_party_confusion_fp": fp,
        "winner_party_confusion_fn": fn,
    }


def area_winner_accuracy(rows: list[Mapping[str, object]]) -> dict[str, object]:
    """Accuracy of picking the single winning party within each area.

    This is the metric a reader intuitively means by "did the model call the
    seat correctly", as distinct from ``winner_party_row_accuracy`` which also
    rewards correctly rejecting every losing party and is therefore inflated
    by class imbalance (see Hanretty 2021, Table 3, "seats correctly
    predicted" vs a row-level score).
    """

    by_area: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        by_area[(str(row["election_id"]), str(row["division_id"]))].append(row)
    correct = 0
    for area_rows in by_area.values():
        predicted = [row for row in area_rows if row["predicted_party_elected"] == "Yes"]
        actual = [row for row in area_rows if row["actual_party_elected"] == "Yes"]
        if len(predicted) != 1 or len(actual) != 1:
            raise ValueError(
                "Single-member winner cohort does not contain one predicted and actual winner."
            )
        correct += predicted[0]["standard_party_name"] == actual[0]["standard_party_name"]
    return {
        "winner_areas_scored": len(by_area),
        "winner_area_accuracy": correct / len(by_area) if by_area else None,
        "winner_areas_correct": correct,
    }


def grouped_metrics(
    rows: list[Mapping[str, object]],
    field: str,
    metric_function,
) -> list[dict[str, object]]:
    """Apply ``metric_function`` once per distinct value of ``field``.

    Re-using one metric definition for every election, year and election type
    means an aggregate figure can never hide a weak subgroup: whatever
    ``metric_function`` reports overall, it also reports per group.
    """

    grouped: dict[object, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[row[field]].append(row)
    return [
        {field: value, **metric_function(group)}
        for value, group in sorted(grouped.items(), key=lambda item: str(item[0]))
    ]


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _f1(true_positive: int, false_positive: int, false_negative: int) -> float | None:
    denominator = 2 * true_positive + false_positive + false_negative
    return 2 * true_positive / denominator if denominator else None
