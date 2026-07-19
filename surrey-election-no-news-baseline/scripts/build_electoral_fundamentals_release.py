"""Generate the Electoral Fundamentals Feature Table release package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from no_news_baseline.electoral_fundamentals_release import (
    create_electoral_fundamentals_release,
)


REPOSITORY_ROOT = PROJECT_ROOT.parent
EXTRACTOR_OUTPUTS = REPOSITORY_ROOT / "surrey-election-extractor" / "outputs"
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/electoral_fundamentals"


def build_release(output_directory: Path = DEFAULT_OUTPUT_DIRECTORY) -> tuple[Path, ...]:
    """Run the release from the four extractor-owned, read-only inputs."""

    return create_electoral_fundamentals_release(
        feature_path=EXTRACTOR_OUTPUTS
        / "no_news_party_contests/no_news_party_contest_features.json",
        target_path=EXTRACTOR_OUTPUTS
        / "no_news_party_contests/no_news_party_contest_targets.json",
        master_path=EXTRACTOR_OUTPUTS
        / "master_surrey_election_database/master_election_database_payload.json",
        overlap_path=EXTRACTOR_OUTPUTS
        / "geographic_overlap_audit/historical_to_2026_spatial_overlap_audit.json",
        output_directory=output_directory,
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help="Directory for the generated CSV files and quality report.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    paths = build_release(_arguments().output_directory)
    for path in paths:
        print(path)
