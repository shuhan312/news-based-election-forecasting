"""Generate the local, review-only dataset for historic-to-2026 geography.

This script consumes public GIS and legal-boundary evidence but deliberately
does not update the master database.  It is a reproducible input to human
review, not an automated approval or historical-comparison workflow.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # Direct execution uses the checked-out package without requiring a global
    # installation.  This changes Python import lookup only.
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.geographic_mapping_review import (
    build_geographic_mapping_review,
    geographic_mapping_review_dataset,
    geographic_mapping_review_markdown,
    geographic_mapping_review_summary,
)
from election_extractor.geographic_overlap_audit import (
    boundary_areas_from_geojson,
    build_geographic_overlap_audit,
    fetch_public_geojson,
    load_overlap_audit_configuration,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/geographic_mapping_review"


def generate_geographic_mapping_review(
    output_directory: Path = OUTPUT_DIRECTORY,
) -> tuple[Path, Path, dict[str, object]]:
    """Write one complete GIS review dataset and a readable companion report."""

    configuration = load_overlap_audit_configuration()
    historical_areas = boundary_areas_from_geojson(
        fetch_public_geojson(configuration.historical_source),
        configuration.historical_source,
    )
    current_areas = tuple(
        area
        for source in configuration.current_sources
        for area in boundary_areas_from_geojson(fetch_public_geojson(source), source)
    )
    overlap_audit = build_geographic_overlap_audit(
        configuration,
        historical_areas,
        current_areas,
    )
    review_rows = build_geographic_mapping_review(overlap_audit)
    dataset = geographic_mapping_review_dataset(
        review_rows,
        geographic_mapping_review_summary(review_rows),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "geographic_mapping_review_dataset.json"
    markdown_path = output_directory / "geographic_mapping_review_report.md"
    json_path.write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(geographic_mapping_review_markdown(dataset), encoding="utf-8")
    return json_path, markdown_path, dataset


def main() -> None:
    """Generate reports and print only their locations plus review totals."""

    json_path, markdown_path, dataset = generate_geographic_mapping_review()
    summary = dataset["summary"]
    assert isinstance(summary, dict)
    print(
        json.dumps(
            {
                "json": str(json_path),
                "markdown": str(markdown_path),
                "total_overlaps_reviewed": summary["total_overlaps_reviewed"],
                "requires_review_mappings": summary["requires_review_mappings"],
                "final_geographic_mapping_rows_created": summary[
                    "final_geographic_mapping_rows_created"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
