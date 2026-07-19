"""Tests for the population-weighted crosswalk's scientific boundaries."""

from __future__ import annotations

from election_extractor.population_weighted_crosswalk import (
    build_population_weighted_crosswalk_audit,
)


def _polygon(name: str, x0: float, x1: float, *, field: str) -> dict[str, object]:
    """Create a small rectangular boundary feature for deterministic tests."""

    return {
        "type": "Feature",
        "properties": {field: name},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[x0, 0], [x1, 0], [x1, 1], [x0, 1], [x0, 0]]],
        },
    }


def _point(code: str, x: float) -> dict[str, object]:
    """Create one synthetic population-weighted Output Area centroid."""

    return {
        "type": "Feature",
        "properties": {"OA21CD": code},
        "geometry": {"type": "Point", "coordinates": [x, 0.5]},
    }


def _candidate(election: str, area: str, party: str, votes: int) -> dict[str, object]:
    """Create the minimal official-result fields required by the estimator."""

    return {
        "election_id": election,
        "division_name": area,
        "standard_party_name": party,
        "votes": votes,
    }


def _audit() -> dict[str, object]:
    """Build one unchanged ward and one genuinely changed ward."""

    historical = {
        "type": "FeatureCollection",
        "features": [
            _polygon("Old A", 0, 1, field="CED23NM"),
            _polygon("Old B", 1, 2, field="CED23NM"),
        ],
    }
    current = {
        "type": "FeatureCollection",
        "features": [
            _polygon("Direct", 0, 1, field="Name"),
            _polygon("Changed", 1, 2, field="Name"),
        ],
    }
    # Old B's populations are deliberately unequal. This verifies that votes
    # are reallocated with population weights rather than averaging percentages.
    centroids = {
        "type": "FeatureCollection",
        "features": [_point("OA1", 0.5), _point("OA2", 1.25), _point("OA3", 1.75)],
    }
    candidates = [
        _candidate("surrey-county-council-2021", "Old A", "Alpha", 60),
        _candidate("surrey-county-council-2021", "Old A", "Beta", 40),
        _candidate("surrey-county-council-2021", "Old B", "Alpha", 20),
        _candidate("surrey-county-council-2021", "Old B", "Beta", 80),
        _candidate("target", "Direct", "Alpha", 1),
        _candidate("target", "Beta", "Beta", 1),
        _candidate("target", "Changed", "Alpha", 1),
        _candidate("target", "Changed", "Beta", 1),
    ]
    return build_population_weighted_crosswalk_audit(
        historical_geojson=historical,
        current_geojson_by_election={"target": current},
        oa_centroid_geojson=centroids,
        oa_population={"OA1": 100, "OA2": 25, "OA3": 75},
        candidate_results=candidates,
        approved_direct_mappings=(
            {
                "current_election_id": "target",
                "current_area_name": "Direct",
                "previous_area_name": "Old A",
            },
        ),
    )


def test_changed_boundary_estimate_is_sensitivity_only() -> None:
    """A numeric proxy must never silently become a primary baseline value."""

    audit = _audit()
    changed = next(
        row for row in audit["ward_decisions"] if row["current_area_name"] == "Changed"
    )
    assert changed["primary_history_decision"] == (
        "unavailable_after_official_weight_review"
    )
    assert changed["population_estimate_role"] == "sensitivity_analysis_only"
    assert audit["methodological_decision"]["official_nulls_overwritten"] is False


def test_direct_validation_does_not_claim_split_boundary_validity() -> None:
    """Zero error on an unchanged ward is a pipeline check, not split ground truth."""

    validation = _audit()["validation"]
    assert validation["pipeline_check"] == "passed"
    assert validation["mae_percentage_points"] == 0.0
    assert validation["external_validity_for_changed_boundaries"] == "not_established"


def test_crosswalk_uses_population_weighted_votes() -> None:
    """The audit records source weights and derives shares from weighted votes."""

    audit = _audit()
    assert audit["scope"]["assigned_output_areas"] == 3
    assert audit["scope"]["assigned_population"] == 200
    estimate = next(
        row
        for row in audit["party_share_estimates"]
        if row["current_area_name"] == "changed"
        and row["standard_party_name"] == "Alpha"
    )
    assert estimate["estimated_previous_party_vote_share"] == 20.0


def test_boundary_point_is_rejected_as_ambiguous() -> None:
    """A centroid on two polygon edges is not assigned by an arbitrary tie-break."""

    historical = {
        "type": "FeatureCollection",
        "features": [
            _polygon("A", 0, 1, field="CED23NM"),
            _polygon("B", 1, 2, field="CED23NM"),
        ],
    }
    current = {
        "type": "FeatureCollection",
        "features": [_polygon("Target", 0, 2, field="Name")],
    }
    try:
        build_population_weighted_crosswalk_audit(
            historical_geojson=historical,
            current_geojson_by_election={"target": current},
            oa_centroid_geojson={"type": "FeatureCollection", "features": [_point("X", 1)]},
            oa_population={"X": 1},
            candidate_results=(),
            approved_direct_mappings=(),
        )
    except ValueError as error:
        assert "non-unique" in str(error)
    else:
        raise AssertionError("Ambiguous OA assignment was not rejected.")
