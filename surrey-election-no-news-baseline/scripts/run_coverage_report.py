"""Run Task 3: join the coverage-evaluation universe to the N0-N3 predictions.

Writes two CSVs:

- ``model_predictions_coverage.csv``: long format, one row per
  (party_contest_id, model_id) - the full join with cohort, eligibility,
  prediction presence/validity, error and exclusion reason.
- ``model_comparison.csv``: one row per model, with target/eligible/valid
  counts, both coverage measures, own-covered-sample MAE, common-sample MAE
  and winner metrics where available.

Same input contract as the other benchmark runners in this project.
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

from no_news_baseline.coverage_report import (
    MODEL_IDS,
    common_sample_metrics,
    run_all_models_and_build_coverage_table,
    summarise_coverage,
    winner_coverage_metrics,
)


REPOSITORY_ROOT = PROJECT_ROOT.parent
DEFAULT_INPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "surrey-election-extractor"
    / "outputs"
    / "no_news_party_contests"
)
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/coverage_report"

COVERAGE_ROW_COLUMNS = (
    "party_contest_id",
    "model_id",
    "primary_cohort",
    "election_id",
    "election_type",
    "theoretically_eligible",
    "prediction_present",
    "prediction_valid",
    "actual_party_vote_share",
    "predicted_party_vote_share",
    "absolute_share_error",
    "reason",
)

COMPARISON_COLUMNS = (
    "model_id",
    "target_observation_count",
    "eligible_observation_count",
    "valid_prediction_count",
    "target_universe_coverage",
    "eligibility_conditioned_coverage",
    "own_covered_sample_mae",
    "common_sample_count",
    "common_sample_mae",
    "winner_available",
    "winner_eligible_area_count",
    "winner_predicted_area_count",
    "winner_coverage",
    "winner_accuracy",
)


def run_coverage_report(
    feature_path: Path,
    target_path: Path,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    l2_penalty: float = 1.0,
) -> tuple[Path, Path]:
    feature_payload = json.loads(feature_path.read_text(encoding="utf-8"))
    target_payload = json.loads(target_path.read_text(encoding="utf-8"))
    features = feature_payload.get("rows")
    targets = target_payload.get("rows")
    if not isinstance(features, list) or not isinstance(targets, list):
        raise ValueError("Feature and target JSON files must each contain a rows list.")

    coverage_rows, join_report = run_all_models_and_build_coverage_table(
        features, targets, l2_penalty
    )
    if join_report["mismatch_count"]:
        # Mismatches are written to the audit JSON below rather than
        # silently swallowed; this print is a visible flag during
        # reproduction runs.
        print(f"WARNING: {join_report['mismatch_count']} join mismatch(es) detected.")

    summary = summarise_coverage(coverage_rows)
    common = common_sample_metrics(features, targets, l2_penalty)
    winners = winner_coverage_metrics(features, targets)

    output_directory.mkdir(parents=True, exist_ok=True)

    coverage_path = output_directory / "model_predictions_coverage.csv"
    with coverage_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COVERAGE_ROW_COLUMNS)
        writer.writeheader()
        for row in coverage_rows:
            writer.writerow({column: row.get(column) for column in COVERAGE_ROW_COLUMNS})

    comparison_path = output_directory / "model_comparison.csv"
    with comparison_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMPARISON_COLUMNS)
        writer.writeheader()
        for model_id in MODEL_IDS:
            overall = summary[model_id]["overall"]
            common_metrics = common["common_support_share_metrics"][model_id]
            winner = winners[model_id]
            writer.writerow(
                {
                    "model_id": model_id,
                    "target_observation_count": overall["target_count"],
                    "eligible_observation_count": overall["theoretically_eligible_count"],
                    "valid_prediction_count": overall["valid_prediction_count"],
                    "target_universe_coverage": overall["target_universe_coverage"],
                    "eligibility_conditioned_coverage": overall[
                        "eligibility_conditioned_coverage"
                    ],
                    "own_covered_sample_mae": overall["own_covered_sample_mae"],
                    "common_sample_count": common["shared_contest_count"],
                    "common_sample_mae": common_metrics["party_share_mae_percentage_points"],
                    "winner_available": winner["available"],
                    "winner_eligible_area_count": winner.get("winner_eligible_area_count"),
                    "winner_predicted_area_count": winner.get("winner_predicted_area_count"),
                    "winner_coverage": winner.get("winner_coverage"),
                    "winner_accuracy": winner.get("winner_accuracy"),
                }
            )

    audit_path = output_directory / "coverage_report_audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "join_report": join_report,
                "coverage_by_cohort": summary,
            },
            indent=2,
        )
        + "\n"
    )

    return coverage_path, comparison_path


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features", type=Path, default=DEFAULT_INPUT_DIRECTORY / "no_news_party_contest_features.json"
    )
    parser.add_argument(
        "--targets", type=Path, default=DEFAULT_INPUT_DIRECTORY / "no_news_party_contest_targets.json"
    )
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--l2-penalty", type=float, default=1.0)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _arguments()
    for path in run_coverage_report(
        arguments.features, arguments.targets, arguments.output_directory, arguments.l2_penalty
    ):
        print(path)
