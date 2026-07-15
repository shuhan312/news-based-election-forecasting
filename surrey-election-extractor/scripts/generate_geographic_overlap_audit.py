"""Generate a local, review-only GIS overlap audit from official public layers."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # Direct script execution needs the project package, but changing sys.path
    # does not modify input data, mappings or the master database.
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.geographic_overlap_audit import (
    boundary_areas_from_geojson,
    build_geographic_overlap_audit,
    fetch_public_geojson,
    geographic_overlap_markdown,
    load_overlap_audit_configuration,
)


OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/geographic_overlap_audit"


def generate_overlap_audit(
    output_directory: Path = OUTPUT_DIRECTORY,
) -> tuple[Path, Path, dict[str, object]]:
    """Fetch official geometries and write local evidence files for manual review."""

    configuration = load_overlap_audit_configuration()
    historical_areas = boundary_areas_from_geojson(
        fetch_public_geojson(configuration.historical_source),
        configuration.historical_source,
    )
    current_area_groups = [
        boundary_areas_from_geojson(fetch_public_geojson(source), source)
        for source in configuration.current_sources
    ]
    current_areas = tuple(
        area for area_group in current_area_groups for area in area_group
    )
    audit = build_geographic_overlap_audit(
        configuration,
        historical_areas,
        current_areas,
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "historical_to_2026_spatial_overlap_audit.json"
    markdown_path = output_directory / "historical_to_2026_spatial_overlap_audit.md"
    json_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(geographic_overlap_markdown(audit), encoding="utf-8")
    return json_path, markdown_path, audit


def main() -> None:
    """Generate reports and display only compact reproducibility information."""

    json_path, markdown_path, audit = generate_overlap_audit()
    coverage = audit["coverage"]
    assert isinstance(coverage, dict)
    print(
        json.dumps(
            {
                "json": str(json_path),
                "markdown": str(markdown_path),
                "status": audit["status"],
                "candidate_overlap_rows": coverage["candidate_overlap_rows"],
                "final_mapping_rows": len(audit["verified_geographic_mapping_rows"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
