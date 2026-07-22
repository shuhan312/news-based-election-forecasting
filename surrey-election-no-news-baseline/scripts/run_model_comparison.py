"""Run the four-way no-news model comparison from the extractor data contract.

Same input contract and argparse shape as the other benchmark runners, so
the head-to-head comparison is produced the same way as everything else it
compares.
"""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from no_news_baseline.model_comparison import compare_models_on_common_support


REPOSITORY_ROOT = PROJECT_ROOT.parent
DEFAULT_INPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "surrey-election-extractor"
    / "outputs"
    / "no_news_party_contests"
)
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/model_comparison"


def run_model_comparison(
    feature_path: Path,
    target_path: Path,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    l2_penalty: float = 1.0,
) -> Path:
    """Read the versioned data contract and write the comparison JSON."""

    feature_payload = json.loads(feature_path.read_text(encoding="utf-8"))
    target_payload = json.loads(target_path.read_text(encoding="utf-8"))
    features = feature_payload.get("rows")
    targets = target_payload.get("rows")
    if not isinstance(features, list) or not isinstance(targets, list):
        raise ValueError("Feature and target JSON files must each contain a rows list.")

    comparison = compare_models_on_common_support(features, targets, l2_penalty)
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / "no_news_model_comparison.json"
    output_path.write_text(json.dumps(comparison, indent=2) + "\n")
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
        help="Directory for the generated comparison JSON.",
    )
    parser.add_argument(
        "--l2-penalty",
        type=float,
        default=1.0,
        help="Ridge L2 penalty used for the fitted model in the comparison.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _arguments()
    print(
        run_model_comparison(
            arguments.features,
            arguments.targets,
            arguments.output_directory,
            arguments.l2_penalty,
        )
    )
