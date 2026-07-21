"""Run the fold-by-fold benchmark report from the extractor data contract.

Structured the same way as the other benchmark runners in this project (same
input files, same argparse shape) so a reader can see this is evaluated the
same way as everything else, not with a bespoke ad hoc script.
"""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from no_news_baseline.temporal_validation_report import score_benchmarks_across_folds


REPOSITORY_ROOT = PROJECT_ROOT.parent
DEFAULT_INPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "surrey-election-extractor"
    / "outputs"
    / "no_news_party_contests"
)
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/temporal_validation"


def run_temporal_validation_report(
    feature_path: Path,
    target_path: Path,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
) -> Path:
    """Read the versioned data contract and write the per-fold report."""

    feature_payload = json.loads(feature_path.read_text(encoding="utf-8"))
    target_payload = json.loads(target_path.read_text(encoding="utf-8"))
    features = feature_payload.get("rows")
    targets = target_payload.get("rows")
    if not isinstance(features, list) or not isinstance(targets, list):
        raise ValueError("Feature and target JSON files must each contain a rows list.")

    fold_rows = score_benchmarks_across_folds(features, targets)
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / "temporal_validation_report.json"
    output_path.write_text(json.dumps({"rows": fold_rows}, indent=2) + "\n")
    return output_path


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features",
        type=Path,
        default=DEFAULT_INPUT_DIRECTORY / "no_news_party_contest_features.json",
        help="Extractor-produced party-contest feature JSON.",
    )
    parser.add_argument(
        "--targets",
        type=Path,
        default=DEFAULT_INPUT_DIRECTORY / "no_news_party_contest_targets.json",
        help="Extractor-produced party-contest target JSON.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help="Directory for the generated per-fold report JSON.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _arguments()
    print(
        run_temporal_validation_report(
            arguments.features,
            arguments.targets,
            arguments.output_directory,
        )
    )
