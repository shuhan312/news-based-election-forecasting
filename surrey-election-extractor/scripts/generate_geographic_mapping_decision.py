"""Generate the review-only Geographic Mapping Decision Framework outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # Direct execution reads the checked-out package only; it does not alter
    # official election records, approved mappings or enrichment outputs.
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.geographic_mapping_decision import (
    GeographicMappingReviewRow,
    build_geographic_mapping_decisions,
    geographic_mapping_decision_dataset,
    geographic_mapping_decision_report_markdown,
    geographic_mapping_methodology_markdown,
    load_mapping_decision_policy,
)
from scripts.generate_geographic_mapping_review import generate_geographic_mapping_review


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/geographic_mapping_decision"


def generate_geographic_mapping_decision_outputs(
    output_directory: Path = OUTPUT_DIRECTORY,
) -> tuple[Path, Path, Path, dict[str, object]]:
    """Regenerate GIS candidates, then document strict analytical decisions only."""

    # Regenerate the review dataset from configured official GIS sources so the
    # decision report cannot silently rely on a stale or manually edited file.
    _, _, review_dataset = generate_geographic_mapping_review()
    raw_rows = review_dataset["review_rows"]
    if not isinstance(raw_rows, list):
        raise ValueError("Geographic mapping review dataset must contain review_rows.")
    review_rows = tuple(GeographicMappingReviewRow(**row) for row in raw_rows)
    policy = load_mapping_decision_policy()
    decisions = build_geographic_mapping_decisions(review_rows, policy)
    dataset = geographic_mapping_decision_dataset(decisions, policy)

    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "geographic_mapping_decision_dataset.json"
    report_path = output_directory / "geographic_mapping_decision_report.md"
    methodology_path = output_directory / "geographic_mapping_methodology.md"
    json_path.write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(
        geographic_mapping_decision_report_markdown(dataset),
        encoding="utf-8",
    )
    methodology_path.write_text(
        geographic_mapping_methodology_markdown(policy),
        encoding="utf-8",
    )
    return json_path, report_path, methodology_path, dataset


def main() -> None:
    """Generate compact status output for the reproducible decision artefacts."""

    json_path, report_path, methodology_path, dataset = (
        generate_geographic_mapping_decision_outputs()
    )
    summary = dataset["summary"]
    assert isinstance(summary, dict)
    print(
        json.dumps(
            {
                "json": str(json_path),
                "report": str(report_path),
                "methodology": str(methodology_path),
                "accepted_direct": summary["accepted_direct_mappings"],
                "requires_review": summary["requires_review_mappings"],
                "approved_direct_mapping_rows": summary[
                    "approved_direct_mapping_rows"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
