"""Run the no-news persistence benchmark from the extractor data contract.

The modelling project deliberately reads generated JSON rather than importing
the extractor's internal Python package.  This keeps the boundary explicit:
the extractor owns evidence and feature publication; this project owns
predictions, metrics and experimental interpretation.
"""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from no_news_baseline.persistence_benchmark import (
    evaluate_previous_result_persistence,
)


REPOSITORY_ROOT = PROJECT_ROOT.parent
DEFAULT_INPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "surrey-election-extractor"
    / "outputs"
    / "no_news_party_contests"
)
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/persistence_benchmark"


def run_persistence_benchmark(
    feature_path: Path,
    target_path: Path,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
) -> Path:
    """Read the versioned data contract and write benchmark outputs."""

    # Read the two extractor-owned files separately.  Features represent
    # pre-election information; targets contain realised results and are used
    # only by the evaluator after each persistence prediction is defined.
    feature_payload = json.loads(feature_path.read_text(encoding="utf-8"))
    target_payload = json.loads(target_path.read_text(encoding="utf-8"))
    features = feature_payload.get("rows")
    targets = target_payload.get("rows")
    if not isinstance(features, list) or not isinstance(targets, list):
        raise ValueError("Feature and target JSON files must each contain a rows list.")
    # Keep the benchmark calculation in the reusable module so that this
    # command-line wrapper only handles files, paths and JSON serialisation.
    predictions, metrics, audit = evaluate_previous_result_persistence(features, targets)
    output_directory.mkdir(parents=True, exist_ok=True)
    # Write a row-level release for inspection, then two smaller summaries for
    # reporting.  These derived files are reproducible and ignored by Git.
    (output_directory / "previous_result_persistence_predictions.json").write_text(
        json.dumps({"rows": predictions}, indent=2) + "\n"
    )
    (output_directory / "previous_result_persistence_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n"
    )
    audit_path = output_directory / "previous_result_persistence_audit.json"
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    return audit_path


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
        help="Directory for generated predictions, metrics and audit JSON.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _arguments()
    print(
        run_persistence_benchmark(
            arguments.features,
            arguments.targets,
            arguments.output_directory,
        )
    )
