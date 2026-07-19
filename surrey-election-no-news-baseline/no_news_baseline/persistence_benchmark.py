"""Evaluate the direct previous-election persistence benchmark.

This is the simplest defensible operationalisation of the supervisor's
``previous election results`` comparator:

* predicted party share = the approved previous exact-label party share;
* predicted elected party = the previous winner, but only when that exact
  political identity is uniquely present on the current ballot.

The benchmark has no fitted parameters.  Every prediction is therefore an
out-of-time historical carry-forward rather than an in-sample model fit.
Rows lacking a unique previous winner on the current ballot remain visible and
are excluded only from winner metrics, never silently assigned to another
party.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from math import sqrt
from statistics import median


PRIMARY_COHORT_STATUS = "eligible_primary_single_member_party_share"


def evaluate_previous_result_persistence(
    features: Iterable[Mapping[str, object]],
    targets: Iterable[Mapping[str, object]],
) -> tuple[tuple[dict[str, object], ...], dict[str, object], dict[str, int]]:
    """Return row predictions, grouped metrics and a transparent audit."""

    feature_rows = list(features)
    target_rows = list(targets)
    target_by_id = {str(row["party_contest_id"]): row for row in target_rows}
    _assert_one_to_one_release(feature_rows, target_rows)

    # The share cohort is deliberately narrower than the winner cohort.  A
    # party-share forecast needs a one-to-one party/candidate interpretation,
    # so only approved single-member contests with one candidate for the party
    # and a usable lagged share enter this particular calculation.
    share_cohort = [
        row for row in feature_rows if row["baseline_eligibility"] == PRIMARY_COHORT_STATUS
    ]
    # Winner persistence requires an approved single-member predecessor but
    # does not require every current party to have a lagged share. Including
    # new/current-only parties avoids inflating accuracy by deleting genuine
    # alternatives from the ballot.
    winner_cohort = [
        row
        for row in feature_rows
        if row["contest_structure"] == "single_member"
        and row["geographic_reference_eligibility"] == "approved_historical_reference"
    ]
    share_ids = {str(row["party_contest_id"]) for row in share_cohort}
    by_area: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in winner_cohort:
        by_area[(str(row["election_id"]), str(row["division_id"]))].append(row)

    # Decide winner eligibility once for the whole area, rather than once per
    # party.  A winner forecast is meaningful only if exactly one current
    # party can be identified as the previous winner.
    winner_status_by_area: dict[tuple[str, str], str] = {}
    for area_key, rows in by_area.items():
        previous_winner_rows = [
            row
            for row in rows
            if row["party_was_previous_winner"] is True
            # A repeated label such as Independent is not a political-identity
            # link and can never support winner persistence by itself.
            and row["party_identity_scope"] != "candidate_specific_independent"
        ]
        winner_status_by_area[area_key] = (
            "eligible_unique_previous_winner_on_current_ballot"
            if len(previous_winner_rows) == 1
            else "unavailable_previous_winner_not_uniquely_on_current_ballot"
        )

    predictions: list[dict[str, object]] = []
    for feature in winner_cohort:
        # ``feature`` contains only information intended to be available
        # before the target election.  ``target`` is kept in a separate file
        # and is accessed here only after the prediction has been fixed, so it
        # can be used to score the historical back-test rather than to predict.
        target = target_by_id[str(feature["party_contest_id"])]
        share_eligible = str(feature["party_contest_id"]) in share_ids
        previous_share = (
            _required_number(feature, "previous_party_vote_share") if share_eligible else None
        )
        target_share = _required_number(target, "target_party_vote_share")
        area_key = (str(feature["election_id"]), str(feature["division_id"]))
        winner_status = winner_status_by_area[area_key]
        predicted_elected = (
            "Yes" if feature["party_was_previous_winner"] is True else "No"
        ) if winner_status.startswith("eligible_") else "Unknown"
        # Signed error records whether the persistence rule over- or
        # under-predicted.  Absolute and squared versions are retained for MAE
        # and RMSE respectively.
        error = previous_share - target_share if previous_share is not None else None
        predictions.append(
            {
                "party_contest_id": feature["party_contest_id"],
                "election_id": feature["election_id"],
                "election_year": feature["election_year"],
                "election_type": feature["election_type"],
                "division_id": feature["division_id"],
                "division_name": feature["division_name"],
                "standard_party_name": feature["standard_party_name"],
                "benchmark_id": "previous_result_persistence_v1",
                "predicted_party_vote_share": previous_share,
                "actual_party_vote_share": target_share,
                "share_error": error,
                "absolute_share_error": abs(error) if error is not None else None,
                "squared_share_error": error**2 if error is not None else None,
                "winner_prediction_status": winner_status,
                "predicted_party_elected": predicted_elected,
                "actual_party_elected": target["target_party_elected"],
                "winner_prediction_correct": (
                    predicted_elected == target["target_party_elected"]
                    if predicted_elected != "Unknown"
                    else None
                ),
                "feature_source_url": feature["historical_source_url"],
                "target_source_urls": target["target_source_urls"],
            }
        )

    _assert_prediction_integrity(predictions, by_area)
    metrics = {
        "benchmark_id": "previous_result_persistence_v1",
        "research_interpretation": (
            "Direct out-of-time carry-forward of approved previous results; "
            "no parameters are fitted and no current-election field is used as a predictor."
        ),
        "overall": _metrics_for_predictions(predictions),
        "by_election": _grouped_metrics(predictions, "election_id"),
        "by_election_year": _grouped_metrics(predictions, "election_year"),
        "by_election_type": _grouped_metrics(predictions, "election_type"),
    }
    audit = _audit(predictions, by_area)
    return tuple(predictions), metrics, audit


def _metrics_for_predictions(rows: list[Mapping[str, object]]) -> dict[str, object]:
    # A share metric is calculated only where an approved lagged share exists.
    # Winner metrics can use a wider cohort, because they require only a
    # uniquely identifiable previous winner on the current ballot.
    share_rows = [row for row in rows if row["predicted_party_vote_share"] is not None]
    absolute_errors = [float(row["absolute_share_error"]) for row in share_rows]
    squared_errors = [float(row["squared_share_error"]) for row in share_rows]
    signed_errors = [float(row["share_error"]) for row in share_rows]
    winner_rows = [row for row in rows if row["predicted_party_elected"] != "Unknown"]

    result: dict[str, object] = {
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
        "winner_party_rows_scored": len(winner_rows),
        "winner_party_rows_unscored": len(rows) - len(winner_rows),
    }
    result.update(_binary_metrics(winner_rows))
    result.update(_area_winner_metrics(winner_rows))
    return result


def _binary_metrics(rows: list[Mapping[str, object]]) -> dict[str, object]:
    if not rows:
        return {
            "winner_party_row_accuracy": None,
            "winner_party_balanced_accuracy": None,
            "winner_party_macro_f1": None,
            "winner_party_hard_brier_score": None,
        }
    # Each party row becomes a binary classification: did this party win the
    # single-member contest?  The area-level result below remains the more
    # intuitive measure, while these values make false positives/negatives
    # visible for diagnostic purposes.
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
        # The persistence rule emits deterministic 0/1 decisions rather than
        # calibrated probabilities. This Brier score is therefore labelled
        # ``hard`` and must not be confused with probabilistic calibration.
        "winner_party_hard_brier_score": (fp + fn) / len(rows),
        "winner_party_confusion_tp": tp,
        "winner_party_confusion_tn": tn,
        "winner_party_confusion_fp": fp,
        "winner_party_confusion_fn": fn,
    }


def _area_winner_metrics(rows: list[Mapping[str, object]]) -> dict[str, object]:
    by_area: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        by_area[(str(row["election_id"]), str(row["division_id"]))].append(row)
    correct = 0
    for area_rows in by_area.values():
        # This assertion protects the single-member estimand: each scored area
        # must have exactly one predicted winner and exactly one official
        # winner.  Multi-member wards never enter this benchmark.
        predicted = [row for row in area_rows if row["predicted_party_elected"] == "Yes"]
        actual = [row for row in area_rows if row["actual_party_elected"] == "Yes"]
        if len(predicted) != 1 or len(actual) != 1:
            raise ValueError("Single-member winner cohort does not contain one predicted and actual winner.")
        correct += predicted[0]["standard_party_name"] == actual[0]["standard_party_name"]
    return {
        "winner_areas_scored": len(by_area),
        "winner_area_accuracy": correct / len(by_area) if by_area else None,
        "winner_areas_correct": correct,
    }


def _grouped_metrics(
    rows: list[Mapping[str, object]], field: str
) -> list[dict[str, object]]:
    # Re-use the same metric definitions for each election, year and election
    # type so that aggregate performance cannot hide a weak subgroup.
    grouped: dict[object, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[row[field]].append(row)
    return [
        {field: value, **_metrics_for_predictions(group)}
        for value, group in sorted(grouped.items(), key=lambda item: str(item[0]))
    ]


def _assert_one_to_one_release(
    features: list[Mapping[str, object]], targets: list[Mapping[str, object]]
) -> None:
    # The two extractor outputs are a paired release.  Matching identifiers
    # prevent a target result from being attached to the wrong party/area.
    feature_ids = [str(row["party_contest_id"]) for row in features]
    target_ids = [str(row["party_contest_id"]) for row in targets]
    if len(feature_ids) != len(set(feature_ids)) or len(target_ids) != len(set(target_ids)):
        raise ValueError("Party-contest release contains duplicate identifiers.")
    if set(feature_ids) != set(target_ids):
        raise ValueError("Feature and target party-contest identifiers do not match.")


def _assert_prediction_integrity(
    predictions: list[Mapping[str, object]],
    eligible_areas: Mapping[tuple[str, str], list[Mapping[str, object]]],
) -> None:
    # Do not silently lose an eligible party row while constructing the final
    # release.  A missing row would bias both party-level and area-level scores.
    if len(predictions) != sum(len(rows) for rows in eligible_areas.values()):
        raise ValueError("A winner-cohort party row was lost during prediction.")
    if len({row["party_contest_id"] for row in predictions}) != len(predictions):
        raise ValueError("Persistence predictions contain duplicate identifiers.")
    for row in predictions:
        predicted_share = row["predicted_party_vote_share"]
        if predicted_share is not None and not 0 <= float(predicted_share) <= 100:
            raise ValueError("Predicted share lies outside 0-100.")
        if row["predicted_party_elected"] == "Unknown" and row["winner_prediction_correct"] is not None:
            raise ValueError("An unavailable winner prediction was scored.")


def _audit(
    predictions: list[Mapping[str, object]],
    areas: Mapping[tuple[str, str], list[Mapping[str, object]]],
) -> dict[str, int]:
    # The audit deliberately reports both row and area counts.  One area has
    # several party rows, so reporting only one of these levels could make the
    # eligible prediction population look larger or smaller than it is.
    counts = Counter(
        {
            "primary_party_share_rows": sum(
                row["predicted_party_vote_share"] is not None for row in predictions
            ),
            "winner_party_rows": len(predictions),
            "primary_single_member_areas": len(areas),
        }
    )
    for row in predictions:
        counts[f"winner_status_{row['winner_prediction_status']}"] += 1
    area_status = {
        (str(row["election_id"]), str(row["division_id"])): row["winner_prediction_status"]
        for row in predictions
    }
    for status in area_status.values():
        counts[f"winner_area_status_{status}"] += 1
    return dict(sorted(counts.items()))


def _required_number(row: Mapping[str, object], field: str) -> float:
    # Eligibility should already guarantee this value.  Failing loudly here
    # catches a broken extractor release instead of treating a missing share as
    # zero or dropping it without explanation.
    value = row.get(field)
    if not isinstance(value, (int, float)):
        raise ValueError(f"Primary persistence cohort has no numeric {field}.")
    return float(value)


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _f1(true_positive: int, false_positive: int, false_negative: int) -> float | None:
    denominator = 2 * true_positive + false_positive + false_negative
    return 2 * true_positive / denominator if denominator else None
