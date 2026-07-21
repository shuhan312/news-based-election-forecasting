"""Run both non-geographic naive benchmarks from the extractor data contract.

Mirrors ``run_persistence_benchmark.py`` deliberately: same input contract,
same JSON file layout, same command-line shape. Keeping the two runners
structurally identical makes it easy for a reader (or a later comparison
script) to see that both benchmark families were evaluated the same way.
"""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from no_news_baseline.naive_benchmarks import (
    evaluate_equal_share_reference,
    evaluate_party_historical_mean_reference,
)


REPOSITORY_ROOT = PROJECT_ROOT.parent
DEFAULT_INPUT_DIRECTORY = (
    REPOSITORY_ROOT
    / "surrey-election-extractor"
    / "outputs"
    / "no_news_party_contests"
)
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/naive_benchmarks"

# Each entry pairs a benchmark function with the output-file stem it writes
# to. Both benchmarks share one input contract, so this loop-driven layout
# avoids writing the same file-handling logic out twice.
BENCHMARKS = (
    ("equal_share_reference", evaluate_equal_share_reference),
    ("party_historical_mean_reference", evaluate_party_historical_mean_reference),
)


def run_naive_benchmarks(
    feature_path: Path,
    target_path: Path,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
) -> tuple[Path, ...]:
    """Read the versioned data contract once and write both benchmarks' outputs."""

    feature_payload = json.loads(feature_path.read_text(encoding="utf-8"))
    target_payload = json.loads(target_path.read_text(encoding="utf-8"))
    features = feature_payload.get("rows")
    targets = target_payload.get("rows")
    if not isinstance(features, list) or not isinstance(targets, list):
        raise ValueError("Feature and target JSON files must each contain a rows list.")

    output_directory.mkdir(parents=True, exist_ok=True)
    audit_paths: list[Path] = []
    for name, evaluate in BENCHMARKS:
        # Re-reading the same lists for each benchmark (rather than mutating
        # them) keeps the two evaluations fully independent, so a bug in one
        # benchmark's handling of the rows cannot leak into the other's.
        predictions, metrics, audit = evaluate(features, targets)
        (output_directory / f"{name}_predictions.json").write_text(
            json.dumps({"rows": predictions}, indent=2) + "\n"
        )
        (output_directory / f"{name}_metrics.json").write_text(
            json.dumps(metrics, indent=2) + "\n"
        )
        audit_path = output_directory / f"{name}_audit.json"
        audit_path.write_text(json.dumps(audit, indent=2) + "\n")
        audit_paths.append(audit_path)
    return tuple(audit_paths)


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
    for path in run_naive_benchmarks(
        arguments.features,
        arguments.targets,
        arguments.output_directory,
    ):
        print(path)
