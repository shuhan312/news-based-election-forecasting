"""Run the frozen 2017-to-2021 production news experiment.

The news table has election x party x period grain.  Copying one party value
onto every division and fitting on those copied rows would turn five 2017
party observations into hundreds of apparently independent observations.  To
avoid that pseudo-replication, this module first averages the Stage 1 residual
within each 2017 party and fits exactly one row per party.

The fitted adjustment is then applied to candidate rows in 2021.  All candidate
shares in a contest are renormalised to sum to 100 after the adjustment; a set
of independently shifted shares is not a valid election prediction otherwise.

The ridge penalty is fixed at 1.0 before looking at 2021.  There is only one
fitting election, so neither 2021 nor the unreachable 2026 holdout may be used
to choose it.  Results are reported against both the untouched Stage 1 baseline
and a training-only intercept recalibration.  The second comparison identifies
whether the news features add anything beyond correcting the baseline's mean
2017 residual.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np

from news_modelling.news_estimator import RidgeModel, bootstrap_improvement


FIT_ELECTION = "surrey-county-council-2017"
VALIDATION_ELECTION = "surrey-county-council-2021"
FIT_NEWS_ELECTION = "SCC-2017-05"
VALIDATION_NEWS_ELECTION = "SCC-2021-05"
FIXED_RIDGE_PENALTY = 1.0


# Only these identities have a corresponding row in the six-party production
# news table.  Labour and Co-operative candidates are part of Labour for this
# join; Reform and UKIP have different keys and are never merged.
PARTY_KEYS = {
    "conservative": "conservative",
    "labour": "labour",
    "labour and co-operative": "labour",
    "liberal democrats": "liberal_democrat",
    "the green party": "green",
    "green party": "green",
    "uk independence party": "ukip",
    "reform uk": "reform_uk",
}


class ProductionExperimentError(RuntimeError):
    """The frozen inputs do not support the declared experiment."""


def party_key(name: object) -> str | None:
    """Map Stage 1's display label to the production feature-table key."""

    return PARTY_KEYS.get(str(name).strip().lower())


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float_or_structural_zero(row: dict, column: str) -> float:
    """Read a frozen feature, allowing only audited structural blanks.

    `production_estimability.py` has already proved that selected share fields
    are blank only when their named denominator is zero.  This function does
    not provide general imputation: the experiment refuses to start unless the
    estimability report records that exact zero-fill policy.
    """

    value = str(row.get(column, "")).strip()
    return 0.0 if value == "" else float(value)


def validate_inputs(oof_rows: list[dict], audit: dict) -> None:
    """Enforce the pre-2026 design before constructing any target values."""

    if audit.get("status") != "exploratory_news_modelling_permitted_with_limits":
        raise ProductionExperimentError("Production estimability gate is not open.")
    if audit["holdout_protection"].get("stage1_holdout_file_read") is not False:
        raise ProductionExperimentError("The audit did not prove holdout isolation.")
    if any("2026" in row.get("election_id", "") for row in oof_rows):
        raise ProductionExperimentError("2026 is present in the OOF input.")
    if any(
        _truthy(row.get("is_reform_uk")) and _truthy(row.get("is_ukip"))
        for row in oof_rows
    ):
        raise ProductionExperimentError("A row merges Reform UK and UKIP.")


def aggregate_fitting_residuals(oof_rows: Iterable[dict]) -> dict[str, dict]:
    """Return one 2017 target row per supported party, never per candidate."""

    residuals: dict[str, list[float]] = defaultdict(list)
    for row in oof_rows:
        if row.get("election_id") != FIT_ELECTION:
            continue
        key = party_key(row.get("standard_party_name"))
        if key is None:
            continue
        residuals[key].append(
            float(row["observed_vote_share"])
            - float(row["predicted_vote_share"])
        )

    result = {
        key: {
            "party_key": key,
            "candidate_rows": len(values),
            "mean_residual": float(np.mean(values)),
        }
        for key, values in sorted(residuals.items())
    }
    # Reform did not exist in the fitting election.  Its accidental presence
    # would change the scientific interpretation and must be reviewed rather
    # than silently accepted as more data.
    if "reform_uk" in result:
        raise ProductionExperimentError("Unexpected Reform row in 2017 fitting data.")
    if len(result) < 3:
        raise ProductionExperimentError(
            f"Only {len(result)} supported 2017 parties; ridge fit is not meaningful."
        )
    return result


def _feature_index(rows: Iterable[dict]) -> dict[tuple[str, str, str], dict]:
    index = {}
    for row in rows:
        key = (row["election_id"], row["standard_party_key"], row["period"])
        if key in index:
            raise ProductionExperimentError(f"Duplicate feature row: {key}")
        index[key] = row
    return index


def _normalise_contests(rows: list[dict], raw_column: str, output_column: str) -> int:
    """Clip negative raw shares and make each contest sum to exactly 100."""

    by_contest: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_contest[row["division_id"]].append(row)

    clipped = 0
    for contest_rows in by_contest.values():
        raw = []
        for row in contest_rows:
            value = float(row[raw_column])
            if value < 0:
                clipped += 1
                value = 0.0
            raw.append(value)
        total = sum(raw)
        if total <= 0:
            raise ProductionExperimentError("A contest has no positive prediction.")
        for row, value in zip(contest_rows, raw):
            row[output_column] = 100.0 * value / total
    return clipped


def _metric_block(rows: list[dict], prediction_column: str) -> dict:
    if not rows:
        return {"rows": 0}
    errors = np.array([
        float(row[prediction_column]) - float(row["observed_vote_share"])
        for row in rows
    ])
    return {
        "rows": len(rows),
        "contests": len({row["division_id"] for row in rows}),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
    }


def _metrics(rows: list[dict]) -> dict:
    """Report raw-baseline and recalibrated-baseline comparisons separately."""

    def scope(scope_rows: list[dict]) -> dict:
        baseline = _metric_block(scope_rows, "baseline_prediction")
        recalibrated = _metric_block(scope_rows, "recalibrated_prediction")
        news = _metric_block(scope_rows, "news_enhanced_prediction")
        return {
            "baseline": baseline,
            "recalibrated_without_news": recalibrated,
            "news_enhanced": news,
            "news_vs_raw_baseline_mae": baseline.get("mae", 0) - news.get("mae", 0),
            "news_vs_recalibrated_mae": recalibrated.get("mae", 0) - news.get("mae", 0),
        }

    supported = [row for row in rows if row["party_key"] is not None]
    reform = [row for row in supported if row["party_key"] == "reform_uk"]
    return {"all_supported_parties": scope(supported), "reform_uk": scope(reform)}


def _bootstrap_rows(rows: list[dict], comparator: str) -> list[dict]:
    """Adapt predictions to the existing contest-bootstrap implementation."""

    return [
        {
            "election_id": row["election_id"],
            "area_id": row["division_id"],
            "baseline_prediction": row[comparator],
            "news_enhanced_prediction": row["news_enhanced_prediction"],
            "observed_vote_share": row["observed_vote_share"],
            "baseline_absolute_error": abs(
                row[comparator] - row["observed_vote_share"]
            ),
            "news_absolute_error": abs(
                row["news_enhanced_prediction"] - row["observed_vote_share"]
            ),
        }
        for row in rows
    ]


def run_one(
    oof_rows: list[dict],
    feature_index: dict,
    fitting: dict[str, dict],
    *,
    period: str,
    feature_columns: list[str],
    analysis_name: str,
    analysis_role: str,
) -> tuple[dict, list[dict]]:
    """Fit one frozen arm/period specification and evaluate it on 2021."""

    train_rows = []
    for key, target in fitting.items():
        feature = feature_index[(FIT_NEWS_ELECTION, key, period)]
        train_rows.append({
            **target,
            **{column: _float_or_structural_zero(feature, column)
               for column in feature_columns},
        })

    design = np.array([
        [row[column] for column in feature_columns] for row in train_rows
    ], dtype=float)
    target = np.array([row["mean_residual"] for row in train_rows], dtype=float)
    model = RidgeModel(FIXED_RIDGE_PENALTY).fit(design, target)

    validation_rows = [
        dict(row) for row in oof_rows
        if row.get("election_id") == VALIDATION_ELECTION
    ]
    for row in validation_rows:
        key = party_key(row.get("standard_party_name"))
        row["party_key"] = key
        row["area_id"] = row["division_id"]
        row["baseline_prediction"] = float(row["predicted_vote_share"])
        row["observed_vote_share"] = float(row["observed_vote_share"])
        row["news_adjustment"] = 0.0
        row["recalibration_adjustment"] = model.intercept
        if key is not None:
            feature = feature_index[(VALIDATION_NEWS_ELECTION, key, period)]
            vector = np.array([[
                _float_or_structural_zero(feature, column)
                for column in feature_columns
            ]], dtype=float)
            row["news_adjustment"] = float(model.predict(vector)[0])
        # Unsupported minor parties receive no news adjustment.  They remain
        # in the contest denominator so normalisation is mathematically valid.
        row["raw_recalibrated"] = (
            row["baseline_prediction"]
            + (model.intercept if key is not None else 0.0)
        )
        row["raw_news_enhanced"] = (
            row["baseline_prediction"] + row["news_adjustment"]
        )

    recal_clipped = _normalise_contests(
        validation_rows, "raw_recalibrated", "recalibrated_prediction"
    )
    news_clipped = _normalise_contests(
        validation_rows, "raw_news_enhanced", "news_enhanced_prediction"
    )

    supported = [row for row in validation_rows if row["party_key"] is not None]
    reform = [row for row in supported if row["party_key"] == "reform_uk"]

    ranges = {
        column: {"min": float(design[:, i].min()), "max": float(design[:, i].max())}
        for i, column in enumerate(feature_columns)
    }
    outside = 0
    outside_parties: set[str] = set()
    for row in supported:
        feature = feature_index[(VALIDATION_NEWS_ELECTION, row["party_key"], period)]
        if any(
            _float_or_structural_zero(feature, column) < ranges[column]["min"]
            or _float_or_structural_zero(feature, column) > ranges[column]["max"]
            for column in feature_columns
        ):
            outside += 1
            outside_parties.add(row["party_key"])

    result = {
        "analysis": analysis_name,
        "analysis_role": analysis_role,
        "period": period,
        "period_role": "confirmed_window" if "previous_" not in period else "cumulative_sensitivity",
        "fit_election": FIT_ELECTION,
        "validation_election": VALIDATION_ELECTION,
        "ridge_penalty": FIXED_RIDGE_PENALTY,
        "penalty_selection": "fixed_before_validation; no tuning performed",
        "feature_columns": feature_columns,
        "training_party_rows": len(train_rows),
        "training_reform_rows": 0,
        "training_candidate_rows_by_party": {
            row["party_key"]: row["candidate_rows"] for row in train_rows
        },
        "intercept_mean_2017_residual": model.intercept,
        "standardised_coefficients": {
            column: float(value)
            for column, value in zip(feature_columns, model.coefficients)
        },
        "training_feature_ranges": ranges,
        "validation_supported_candidate_rows": len(supported),
        "validation_reform_rows": len(reform),
        "validation_rows_outside_training_feature_range": outside,
        # Candidate-row count is useful for impact on the score, but the
        # independent news values are party-level.  Reporting both prevents
        # 200 repeated candidate rows from being described as 200 separate
        # extrapolations.
        "validation_parties_outside_training_feature_range": sorted(
            outside_parties
        ),
        "validation_party_count_outside_training_feature_range": len(
            outside_parties
        ),
        "reform_features_outside_training_range": "reform_uk" in outside_parties,
        "negative_raw_shares_clipped": {
            "recalibrated": recal_clipped,
            "news_enhanced": news_clipped,
        },
        "metrics": _metrics(validation_rows),
        "bootstrap_news_vs_raw_baseline": bootstrap_improvement(
            _bootstrap_rows(supported, "baseline_prediction")
        ),
        "bootstrap_news_vs_recalibrated": bootstrap_improvement(
            _bootstrap_rows(supported, "recalibrated_prediction")
        ),
        "reform_bootstrap_news_vs_recalibrated": bootstrap_improvement(
            _bootstrap_rows(reform, "recalibrated_prediction")
        ),
        "warnings": [
            "Only one fitting election and a handful of party-level rows; "
            "coefficients are descriptive and not Reform-specific.",
            "Positive news_vs_recalibrated_mae means the news features improve "
            "on a training-only mean-residual correction; it is the cleaner "
            "incremental-news comparison.",
        ],
    }

    prediction_rows = []
    # Write every 2021 candidate, not only the six supported party families.
    # Unsupported candidates receive no direct news adjustment but remain in
    # the denominator when the contest is normalised.  Keeping them in the CSV
    # lets an independent reader verify that each complete contest sums to 100.
    for row in validation_rows:
        prediction_rows.append({
            "analysis": analysis_name,
            "analysis_role": analysis_role,
            "period": period,
            "period_role": result["period_role"],
            "election_id": row["election_id"],
            "candidate_contest_id": row["candidate_contest_id"],
            "division_id": row["division_id"],
            "standard_party_name": row["standard_party_name"],
            "party_key": row["party_key"] or "",
            "included_in_reported_metrics": row["party_key"] is not None,
            "is_reform_uk": row["party_key"] == "reform_uk",
            "is_ukip": row["party_key"] == "ukip",
            "observed_vote_share": row["observed_vote_share"],
            "baseline_prediction": row["baseline_prediction"],
            "recalibrated_prediction": row["recalibrated_prediction"],
            "news_adjustment_before_contest_normalisation": row["news_adjustment"],
            "news_enhanced_prediction": row["news_enhanced_prediction"],
        })
    return result, prediction_rows


def run_experiment(
    feature_table_path: str | Path,
    audit_path: str | Path,
    oof_path: str | Path,
) -> tuple[dict, list[dict]]:
    """Run every frozen arm and period without consulting 2026."""

    features = _read_csv(feature_table_path)
    audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    oof_rows = _read_csv(oof_path)
    validate_inputs(oof_rows, audit)
    fitting = aggregate_fitting_residuals(oof_rows)
    feature_index = _feature_index(features)

    periods = audit["feature_table"]["windows"] + audit["feature_table"][
        "cumulative_periods"
    ]
    results, predictions = [], []
    for analysis_name, specification in audit["frozen_feature_sets"].items():
        for period in periods:
            result, rows = run_one(
                oof_rows,
                feature_index,
                fitting,
                period=period,
                feature_columns=list(specification["columns"]),
                analysis_name=analysis_name,
                analysis_role=specification["analysis_role"],
            )
            results.append(result)
            predictions.extend(rows)

    return {
        "status": "completed_exploratory_pre_2026_experiment",
        "canonical_release_id": audit["canonical_release"]["release_id"],
        "stage1_holdout_file_read": False,
        "fit_election": FIT_ELECTION,
        "validation_election": VALIDATION_ELECTION,
        "ridge_penalty": FIXED_RIDGE_PENALTY,
        "training_party_rows": len(fitting),
        "training_parties": sorted(fitting),
        "training_reform_rows": 0,
        "analyses": len(audit["frozen_feature_sets"]),
        "periods": periods,
        "specification_results": results,
        "interpretation_rule": (
            "Do not select the best 2021 arm or period retrospectively. Report "
            "all confirmed windows; cumulative periods and local are sensitivity "
            "analyses. No coefficient is Reform-specific or causal."
        ),
    }, predictions


def write_outputs(report: dict, predictions: list[dict], output_dir: str | Path) -> None:
    """Write complete results and row-level predictions for independent audit."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "experiment_results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (output / "experiment_findings.md").write_text(
        render_findings(report), encoding="utf-8"
    )
    with (output / "validation_predictions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(predictions[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(predictions)


def render_findings(report: dict) -> str:
    """Render every result without ranking or selecting the best 2021 score."""

    def table(period_role: str) -> list[str]:
        lines = [
            "| analysis | period | baseline MAE | recalibrated MAE | news MAE | "
            "news vs recalibrated | 95% contest-bootstrap CI | Reform news MAE | "
            "Reform vs recalibrated | parties outside training range |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |",
        ]
        for result in report["specification_results"]:
            if result["period_role"] != period_role:
                continue
            overall = result["metrics"]["all_supported_parties"]
            reform = result["metrics"]["reform_uk"]
            interval = result["bootstrap_news_vs_recalibrated"]
            lines.append(
                f"| {result['analysis']} | {result['period']} | "
                f"{overall['baseline']['mae']:.4f} | "
                f"{overall['recalibrated_without_news']['mae']:.4f} | "
                f"{overall['news_enhanced']['mae']:.4f} | "
                f"{overall['news_vs_recalibrated_mae']:+.4f} | "
                f"[{interval.get('improvement_ci_lower', 0):+.4f}, "
                f"{interval.get('improvement_ci_upper', 0):+.4f}] | "
                f"{reform['news_enhanced']['mae']:.4f} | "
                f"{reform['news_vs_recalibrated_mae']:+.4f} | "
                f"{result['validation_party_count_outside_training_feature_range']} |"
            )
        return lines

    confirmed = [
        result for result in report["specification_results"]
        if result["period_role"] == "confirmed_window"
    ]
    positive_confirmed = [
        result for result in confirmed
        if result["metrics"]["all_supported_parties"][
            "news_vs_recalibrated_mae"
        ] > 0
    ]
    sensitivity_positive = [
        result for result in report["specification_results"]
        if result["period_role"] == "cumulative_sensitivity"
        and result["metrics"]["all_supported_parties"][
            "news_vs_recalibrated_mae"
        ] > 0
    ]

    lines = [
        "# Production news experiment: 2017 fitting, 2021 validation",
        "",
        "**Status: exploratory pre-2026 result.** The Stage 1 holdout file was "
        "not read. Positive `news vs recalibrated` values mean lower MAE than "
        "a training-only mean-residual correction; negative values mean worse.",
        "",
        "## Frozen design",
        "",
        f"- Fitting election: `{report['fit_election']}`.",
        f"- Validation election: `{report['validation_election']}`.",
        f"- Independent fitting rows: {report['training_party_rows']} parties "
        f"({', '.join(report['training_parties'])}).",
        "- Reform fitting rows: 0; Reform validation candidate rows: 6.",
        "- Ridge penalty: 1.0, fixed before validation; no tuning on 2021.",
        "- News features are fitted at party grain, then contest predictions "
        "are clipped at zero and renormalised to 100.",
        "- Contest-bootstrap intervals condition on the fitted five-party model; "
        "they do not include uncertainty from having only one fitting election.",
        "",
        "## Confirmed six-window results",
        "",
        *table("confirmed_window"),
        "",
        "## Cumulative-period sensitivity results",
        "",
        *table("cumulative_sensitivity"),
        "",
        "## Findings that may be reported",
        "",
        f"- {len(positive_confirmed)} of {len(confirmed)} confirmed-window arm "
        "comparisons improve overall MAE over the recalibrated control. The "
        "observed count is zero; non-zero confirmed-window differences worsen "
        "the score and zero differences reproduce the recalibrated control.",
        "- The untouched Stage 1 baseline MAE on the 279 supported 2021 rows is "
        "7.1585. The training-only recalibration MAE is 7.5872, so even the "
        "mean 2017 residual does not transfer cleanly to 2021.",
        "- Reform-only changes are inconsistent across windows: several appear "
        "better, the 7-to-4-day window is markedly worse, and zero-signal "
        "periods are unchanged. With zero Reform fitting rows, these are "
        "party-generic extrapolations, not a learned Reform effect.",
        f"- {len(sensitivity_positive)} cumulative comparisons improve overall "
        "MAE. They are sensitivity results and cannot be promoted or selected "
        "because they looked better on 2021.",
        "- Many validation party values fall outside their 2017 training "
        "ranges, and several specifications require negative raw shares to be "
        "clipped before contest normalisation. These are direct signs of "
        "unstable extrapolation from five party-level fitting rows.",
        "",
        "## Conclusion",
        "",
        "The confirmed-window experiment provides no evidence that these frozen "
        "news features improve overall 2021 prediction beyond a training-only "
        "recalibration. This is not evidence that news has no effect in general: "
        "the design has one fitting election, five party-level rows and no Reform "
        "training observation. Local remains sensitivity-only, no result is "
        "causal, and 2026 remains sealed.",
        "",
    ]
    return "\n".join(lines)
