"""Generate local historical-baseline outputs without changing source data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the documented ``python scripts/...`` command work from the project
# directory without requiring a local editable install or an environment-only
# PYTHONPATH setting.  This affects import resolution only, never source data.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.historical_baseline import (
    baseline_feature_dictionary_markdown,
    baseline_methodology_markdown,
    build_historical_baseline_features,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/historical_baseline_features"


def run(output_directory: Path = OUTPUT_DIRECTORY) -> dict[str, Path]:
    """Write reproducible derived files while preserving completed source audits."""

    baseline = build_historical_baseline_features()
    output_directory.mkdir(parents=True, exist_ok=True)
    files = {
        "feature_schema": output_directory / "historical_baseline_feature_schema.json",
        "feature_table": output_directory / "historical_baseline_feature_table.json",
        "party_history": output_directory / "historical_party_history_features.json",
        "candidate_history": output_directory / "candidate_history_infrastructure.json",
        "readiness": output_directory / "historical_baseline_readiness.json",
        "dictionary": output_directory / "historical_baseline_feature_dictionary.md",
        "methodology": output_directory / "historical_baseline_methodology.md",
    }
    files["feature_schema"].write_text(
        json.dumps({"schema_version": baseline["schema_version"], "feature_schema": baseline["feature_schema"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    files["feature_table"].write_text(
        json.dumps(baseline["baseline_feature_table"], indent=2) + "\n", encoding="utf-8"
    )
    files["party_history"].write_text(
        json.dumps(baseline["party_history_features"], indent=2) + "\n", encoding="utf-8"
    )
    files["candidate_history"].write_text(
        json.dumps(baseline["candidate_history_infrastructure"], indent=2) + "\n", encoding="utf-8"
    )
    files["readiness"].write_text(
        json.dumps({"readiness": baseline["baseline_readiness_dataset"], "safeguards": baseline["safeguards"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    files["dictionary"].write_text(baseline_feature_dictionary_markdown(), encoding="utf-8")
    files["methodology"].write_text(baseline_methodology_markdown(), encoding="utf-8")
    return files


def main() -> None:
    """Print output paths so a local reproducibility run is easy to inspect."""

    for name, path in run().items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
