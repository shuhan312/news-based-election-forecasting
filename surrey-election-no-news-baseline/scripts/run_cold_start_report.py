"""Run N4 (cold-start baseline) and integrate it into the coverage layer.

Writes four outputs under ``outputs/cold_start/``:

- ``n4_predictions.csv``: observation-level predictions with the full
  shrinkage diagnostics required by the task brief.
- ``n4_cohort_evaluation.json``: N4's coverage and MAE, overall and per
  cohort, computed by the same generalised coverage-report join used for
  N0-N3 (not a separate metric implementation).
- ``n4_model_comparison.csv``: the five-model common-sample comparison,
  reusing model_comparison's intersection logic with N4 added.
- ``n4_ablation.json``: unsmoothed Surrey-wide mean vs the shrunk
  estimator, on identical folds and rows.
"""

from __future__ import annotations

import csv
import json
import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from no_news_baseline.cold_start_model import (
    COLD_START_MODEL_ID,
    DEFAULT_SHRINKAGE_LAMBDA,
    ablation_unsmoothed_vs_smoothed,
    evaluate_cold_start_over_folds,
    tag_universe_with_cold_start_eligibility,
)
from no_news_baseline.coverage_evaluation import build_evaluation_universe
from no_news_baseline.coverage_report import (
    ELIGIBILITY_FIELD_BY_MODEL,
    MODEL_IDS,
    build_prediction_coverage_table,
    summarise_coverage,
)
from no_news_baseline.model_comparison import compare_models_on_common_support


REPOSITORY_ROOT = PROJECT_ROOT.parent
DEFAULT_INPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "surrey-election-extractor"
    / "outputs"
    / "no_news_party_contests"
)
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/cold_start"

PREDICTION_COLUMNS = (
    "party_contest_id",
    "election_id",
    "election_year",
    "election_type",
    "division_id",
    "division_name",
    "standard_party_name",
    "contest_structure",
    "historical_observation_count",
    "raw_historical_party_mean",
    "global_prior",
    "shrinkage_weight",
    "smoothed_party_strength",
    "predicted_party_vote_share",
    "actual_party_vote_share",
    "absolute_share_error",
    "prediction_information_cutoff",
    "train_election_count",
    "winner_prediction_status",
    "predicted_party_elected",
    "actual_party_elected",
    "winner_prediction_correct",
)


def run_cold_start_report(
    feature_path: Path,
    target_path: Path,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    shrinkage_lambda: float = DEFAULT_SHRINKAGE_LAMBDA,
    l2_penalty: float = 1.0,
) -> tuple[Path, ...]:
    feature_payload = json.loads(feature_path.read_text(encoding="utf-8"))
    target_payload = json.loads(target_path.read_text(encoding="utf-8"))
    features = feature_payload.get("rows")
    targets = target_payload.get("rows")
    if not isinstance(features, list) or not isinstance(targets, list):
        raise ValueError("Feature and target JSON files must each contain a rows list.")

    predictions = evaluate_cold_start_over_folds(features, targets, shrinkage_lambda)
    universe = tag_universe_with_cold_start_eligibility(
        build_evaluation_universe(features, targets), features, targets
    )
    # One generalised join for N0-N4 together, so N4's cohort figures come
    # from exactly the same classification code as the frozen N0-N3 report.
    coverage_rows, join_report = build_prediction_coverage_table(
        universe,
        {COLD_START_MODEL_ID: predictions},
        model_ids=(COLD_START_MODEL_ID,),
        eligibility_field_by_model={
            **ELIGIBILITY_FIELD_BY_MODEL,
            COLD_START_MODEL_ID: "eligible_n4_cold_start",
        },
    )
    if join_report["mismatch_count"]:
        print(f"WARNING: {join_report['mismatch_count']} join mismatch(es) detected.")

    cohort_summary = summarise_coverage(coverage_rows)[COLD_START_MODEL_ID]
    comparison = compare_models_on_common_support(
        features, targets, l2_penalty, additional_models={COLD_START_MODEL_ID: predictions}
    )
    ablation = ablation_unsmoothed_vs_smoothed(features, targets, shrinkage_lambda)

    output_directory.mkdir(parents=True, exist_ok=True)

    predictions_path = output_directory / "n4_predictions.csv"
    with predictions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PREDICTION_COLUMNS)
        writer.writeheader()
        for row in predictions:
            writer.writerow({column: row.get(column) for column in PREDICTION_COLUMNS})

    cohort_path = output_directory / "n4_cohort_evaluation.json"
    cohort_path.write_text(
        json.dumps(
            {
                "model_id": COLD_START_MODEL_ID,
                "shrinkage_lambda": shrinkage_lambda,
                "join_report": join_report,
                "evaluation": cohort_summary,
            },
            indent=2,
        )
        + "\n"
    )

    comparison_path = output_directory / "n4_model_comparison.csv"
    with comparison_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model_id", "common_sample_count", "common_sample_mae"])
        for model_id in (*MODEL_IDS, COLD_START_MODEL_ID):
            metrics = comparison["common_support_share_metrics"][model_id]
            writer.writerow(
                [
                    model_id,
                    comparison["shared_contest_count"],
                    metrics["party_share_mae_percentage_points"],
                ]
            )

    ablation_path = output_directory / "n4_ablation.json"
    ablation_path.write_text(json.dumps(ablation, indent=2) + "\n")

    return predictions_path, cohort_path, comparison_path, ablation_path


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features", type=Path, default=DEFAULT_INPUT_DIRECTORY / "no_news_party_contest_features.json"
    )
    parser.add_argument(
        "--targets", type=Path, default=DEFAULT_INPUT_DIRECTORY / "no_news_party_contest_targets.json"
    )
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--shrinkage-lambda", type=float, default=DEFAULT_SHRINKAGE_LAMBDA)
    parser.add_argument("--l2-penalty", type=float, default=1.0)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _arguments()
    for path in run_cold_start_report(
        arguments.features,
        arguments.targets,
        arguments.output_directory,
        arguments.shrinkage_lambda,
        arguments.l2_penalty,
    ):
        print(path)
