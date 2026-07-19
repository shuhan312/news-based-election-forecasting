#!/usr/bin/env python3
"""Generate the reviewed 2021-to-2026 population crosswalk audit.

Large official source files are supplied from outside Git so the repository
retains reproducible code and compact audit outputs without committing raw GIS
downloads.  The source directory must contain the filenames documented by the
command-line help.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from election_extractor.population_weighted_crosswalk import (
    build_population_weighted_crosswalk_audit,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAYLOAD = (
    PROJECT_ROOT
    / "outputs/master_surrey_election_database/master_election_database_payload.json"
)
DEFAULT_PERMISSIONS = PROJECT_ROOT / "config/historical_reference_permissions.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/population_weighted_crosswalk"

SOURCE_URLS = {
    "historical_boundaries": (
        "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
        "County_Electoral_Divisions_May_2023_Boundaries_EN_BFC/FeatureServer/0"
    ),
    "current_boundaries": "https://www10.surreycc.gov.uk/electionmap/",
    "oa_population_weighted_centroids": (
        "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
        "OA_December_2021_EW_PWC_V4/FeatureServer/0"
    ),
    "oa_population": "https://www.nomisweb.co.uk/census/2021/bulk",
    "lgbce_surrey_review": "https://www.lgbce.org.uk/all-reviews/surrey",
}


def _load_json(path: Path) -> Any:
    """Read one UTF-8 JSON source used by the reproducible generator."""

    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    """Return a stable input fingerprint for a reproducible audit record."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_centroid_pages(source_directory: Path) -> dict[str, object]:
    """Merge every downloaded ArcGIS page and reject incomplete duplicates."""

    pages = sorted(
        source_directory.glob("oa_page_*.geojson"),
        key=lambda path: int(path.stem.rsplit("_", 1)[1]),
    )
    if not pages:
        raise FileNotFoundError("No oa_page_*.geojson files found in source directory.")
    # ArcGIS was downloaded in 2,000-row pages. Checking the numeric sequence
    # prevents an interrupted download from silently producing a plausible but
    # incomplete Surrey crosswalk, as happened during exploratory inspection.
    offsets = sorted(int(path.stem.rsplit("_", 1)[1]) for path in pages)
    if offsets[0] != 0 or any(
        current - previous != 2000
        for previous, current in zip(offsets, offsets[1:])
    ):
        raise ValueError(f"OA centroid pages are incomplete: offsets={offsets!r}.")
    features: list[object] = []
    codes: set[str] = set()
    page_sizes: list[int] = []
    for path in pages:
        payload = _load_json(path)
        page_features = payload.get("features", [])
        page_sizes.append(len(page_features))
        for feature in page_features:
            code = str(feature.get("properties", {}).get("OA21CD", ""))
            if not code or code in codes:
                raise ValueError(f"Missing or duplicate OA code in {path.name}: {code!r}.")
            codes.add(code)
            features.append(feature)
    if any(size != 2000 for size in page_sizes[:-1]) or not 0 < page_sizes[-1] <= 2000:
        raise ValueError(f"OA centroid page sizes are incomplete: {page_sizes!r}.")
    return {"type": "FeatureCollection", "features": features}


def _load_population(path: Path) -> dict[str, int]:
    """Read Nomis TS001 usual-resident counts keyed by 2021 Output Area."""

    output: dict[str, int] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            code = row["geography code"]
            output[code] = int(row["Residence type: Total; measures: Value"])
    return output


def _markdown_report(audit: dict[str, object]) -> str:
    """Render the compact decision record used by reviewers and future models."""

    scope = audit["scope"]
    validation = audit["validation"]
    decisions = audit["ward_decisions"]
    lines = [
        "# 2021-to-2026 population-weighted crosswalk audit",
        "",
        "## Release decision",
        "",
        "Population-weighted estimates are reproducible **sensitivity-analysis values only**. "
        "They do not replace official NULLs and are not authorised as primary no-news "
        "predictors for changed-boundary wards.",
        "",
        "## Coverage and validation",
        "",
        f"- Historical divisions: {scope['historical_areas']}",
        f"- 2026 wards: {scope['current_areas']}",
        f"- Assigned 2021 Output Areas: {scope['assigned_output_areas']}",
        f"- Assigned usual-resident population: {scope['assigned_population']:,}",
        f"- Approved direct wards: {scope['approved_direct_wards']}",
        f"- Changed-boundary wards: {scope['changed_boundary_wards']}",
        f"- Direct-mapping comparable party rows: {validation['comparable_party_rows']}",
        f"- Direct-mapping MAE: {validation['mae_percentage_points']:.6f} percentage points",
        f"- Maximum direct-mapping error: "
        f"{validation['maximum_absolute_error_percentage_points']:.6f} percentage points",
        "",
        "The zero validation error checks implementation and source alignment because the "
        "validation wards are unchanged. It cannot establish how votes were distributed "
        "inside historical divisions that were split by the 2026 boundaries.",
        "",
        "## Official sources",
        "",
    ]
    lines.extend(f"- {name}: {url}" for name, url in SOURCE_URLS.items())
    lines.extend(["", "## Input fingerprints", ""])
    lines.extend(
        f"- `{row['path']}`: `{row['sha256']}`"
        for row in audit["input_files"]
    )
    lines.extend(
        [
            "",
            "## Ward decisions",
            "",
            "| Election | Ward | Mapping | Primary history | Population estimate role |",
            "|---|---|---|---|---|",
        ]
    )
    for row in decisions:
        lines.append(
            "| {current_election_id} | {current_area_name} | {mapping_class} | "
            "{primary_history_decision} | {population_estimate_role} |".format(**row)
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-directory",
        type=Path,
        required=True,
        help=(
            "Directory containing old_divisions.geojson, east_wards.geojson, "
            "west_wards.geojson, all oa_page_*.geojson pages and "
            "census2021-ts001-oa.csv."
        ),
    )
    parser.add_argument("--payload", type=Path, default=DEFAULT_PAYLOAD)
    parser.add_argument("--permissions", type=Path, default=DEFAULT_PERMISSIONS)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    master = _load_json(args.payload)
    permissions = _load_json(args.permissions)
    source_paths = [
        args.source_directory / "old_divisions.geojson",
        args.source_directory / "east_wards.geojson",
        args.source_directory / "west_wards.geojson",
        args.source_directory / "census2021-ts001-oa.csv",
        *sorted(
            args.source_directory.glob("oa_page_*.geojson"),
            key=lambda path: int(path.stem.rsplit("_", 1)[1]),
        ),
        args.payload,
        args.permissions,
    ]
    audit = build_population_weighted_crosswalk_audit(
        historical_geojson=_load_json(args.source_directory / "old_divisions.geojson"),
        current_geojson_by_election={
            "surrey-county-council-2026-east-surrey": _load_json(
                args.source_directory / "east_wards.geojson"
            ),
            "surrey-county-council-2026-west-surrey": _load_json(
                args.source_directory / "west_wards.geojson"
            ),
        },
        oa_centroid_geojson=_load_centroid_pages(args.source_directory),
        oa_population=_load_population(
            args.source_directory / "census2021-ts001-oa.csv"
        ),
        candidate_results=master["Candidate Results"],
        approved_direct_mappings=permissions["approved_mappings"],
    )
    audit["source_urls"] = SOURCE_URLS
    # Store names and hashes, not machine-specific absolute paths. The record
    # is portable while still detecting any changed source or master payload.
    audit["input_files"] = [
        {"path": path.name, "sha256": _sha256(path)} for path in source_paths
    ]
    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "population_weighted_crosswalk_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.output_directory / "population_weighted_crosswalk_audit.md").write_text(
        _markdown_report(audit), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
