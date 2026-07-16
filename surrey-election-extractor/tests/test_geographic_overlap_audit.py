"""Tests for the review-only historical-to-2026 GIS overlap audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from election_extractor.geographic_overlap_audit import (
    BoundaryArea,
    BoundarySource,
    boundary_areas_from_geojson,
    build_geographic_overlap_audit,
    calculate_spatial_overlap_candidates,
    load_overlap_audit_configuration,
)
from shapely.geometry import box


def _historical_area() -> BoundaryArea:
    return BoundaryArea(
        area_name="Historic Division",
        area_identifier="E05000001",
        geometry=box(0, 0, 10, 10),
        source_url="https://example.test/historical",
    )


def _current_area(name: str, election_id: str, geometry: object) -> BoundaryArea:
    return BoundaryArea(
        area_name=name,
        area_identifier=name,
        geometry=geometry,  # type: ignore[arg-type]
        source_url=f"https://example.test/{election_id}",
        election_id=election_id,
    )


def _configuration(tmp_path: Path):
    path = tmp_path / "overlap.json"
    path.write_text(
        json.dumps(
            {
                "audit_id": "test-overlap",
                "coordinate_reference_system": "EPSG:27700",
                "minimum_reviewable_intersection_square_metres": 1.0,
                "minimum_mutual_overlap_percent": 0.01,
                "historical_source": {
                    "source_name": "Historic source",
                    "source_url": "https://example.test/historic",
                    "name_field": "name",
                    "identifier_field": "id",
                    "expected_feature_count": 1,
                    "expected_area_count": 1,
                },
                "current_sources": [
                    {
                        "election_id": "east-2026",
                        "source_name": "East source",
                        "source_url": "https://example.test/east",
                        "name_field": "name",
                        "identifier_field": "id",
                        "expected_feature_count": 1,
                        "expected_area_count": 1,
                    },
                    {
                        "election_id": "west-2026",
                        "source_name": "West source",
                        "source_url": "https://example.test/west",
                        "name_field": "name",
                        "identifier_field": "id",
                        "expected_feature_count": 1,
                        "expected_area_count": 1,
                    },
                ],
                "legal_2026_source": {
                    "source_name": "Legal source",
                    "source_url": "https://example.test/order",
                    "evidence_text": "Published legal ward definition.",
                },
            }
        ),
        encoding="utf-8",
    )
    return load_overlap_audit_configuration(path)


def test_overlap_candidates_keep_every_non_zero_intersection_for_review() -> None:
    candidates = calculate_spatial_overlap_candidates(
        [_historical_area()],
        [
            _current_area("East Ward", "east-2026", box(0, 0, 6, 10)),
            _current_area("West Ward", "west-2026", box(6, 0, 10, 10)),
        ],
    )

    assert [candidate.current_area_name for candidate in candidates] == [
        "East Ward",
        "West Ward",
    ]
    assert [candidate.previous_area_overlap_percent for candidate in candidates] == [60.0, 40.0]
    assert all(candidate.review_status == "requires_manual_review" for candidate in candidates)
    assert all(candidate.mapping_type == "official_gis_spatial_overlap_candidate" for candidate in candidates)


def test_overlap_audit_never_creates_final_geographic_mapping_rows(tmp_path: Path) -> None:
    audit = build_geographic_overlap_audit(
        _configuration(tmp_path),
        [_historical_area()],
        [_current_area("East Ward", "east-2026", box(0, 0, 10, 10))],
    )

    assert audit["status"] == "manual_review_required"
    assert audit["verified_geographic_mapping_rows"] == []
    assert audit["assessment"]["historical_comparisons_allowed"] is False


def test_sub_square_metre_boundary_slivers_are_not_mapping_candidates() -> None:
    candidates = calculate_spatial_overlap_candidates(
        [_historical_area()],
        [
            _current_area(
                "Tiny overlap",
                "east-2026",
                box(9.95, 0, 20, 10),
            )
        ],
    )

    assert candidates == ()


def test_geojson_parser_preserves_published_values_and_rejects_duplicate_ids() -> None:
    source = BoundarySource(
        source_name="Mock official source",
        source_url="https://example.test/source",
        name_field="Name",
        identifier_field="Code",
        expected_feature_count=1,
        expected_area_count=1,
        election_id="east-2026",
    )
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"Name": "Published Ward", "Code": "W1"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    }

    areas = boundary_areas_from_geojson(payload, source)
    assert areas[0].area_name == "Published Ward"
    assert areas[0].area_identifier == "W1"

    payload["features"].append(payload["features"][0])
    with pytest.raises(ValueError, match="duplicate identifier"):
        boundary_areas_from_geojson(payload, source)


def test_geojson_parser_merges_a_documented_detached_feature() -> None:
    source = BoundarySource(
        source_name="Mock historical source",
        source_url="https://example.test/historical",
        name_field="Name",
        identifier_field="Code",
        expected_feature_count=2,
        expected_area_count=1,
        detached_name_suffix=" (DET)",
    )
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"Name": "Historic ED", "Code": "H1"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            },
            {
                "type": "Feature",
                "properties": {"Name": "Historic ED (DET)", "Code": "H2"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[2, 0], [3, 0], [3, 1], [2, 1], [2, 0]]],
                },
            },
        ],
    }

    areas = boundary_areas_from_geojson(payload, source)
    assert len(areas) == 1
    assert areas[0].area_identifier == "H1"
    assert areas[0].source_feature_identifiers == ("H1", "H2")
    assert areas[0].geometry.area == 2


def test_configuration_requires_distinct_current_election_ids(tmp_path: Path) -> None:
    configuration = _configuration(tmp_path)
    payload = json.loads((tmp_path / "overlap.json").read_text(encoding="utf-8"))
    payload["current_sources"][1]["election_id"] = "east-2026"
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(json.dumps(payload), encoding="utf-8")

    assert configuration.audit_id == "test-overlap"
    with pytest.raises(ValueError, match="duplicate current election IDs"):
        load_overlap_audit_configuration(duplicate_path)
