"""Tests for the non-electoral Geographic Crosswalk Resolution Layer."""

from __future__ import annotations

from dataclasses import asdict

from election_extractor.geographic_crosswalk_resolution import (
    build_geographic_crosswalk_resolution,
    direct_mappings_for_future_approved_use,
    geographic_crosswalk_resolution_dataset,
    load_geographic_crosswalk_resolution_policy,
)
from election_extractor.geographic_mapping_decision import GeographicMappingDecisionRow


def _decision_row(
    mapping_id: str,
    *,
    previous_id: str = "H1",
    current_id: str = "W1",
    previous_overlap: float = 10.0,
    current_overlap: float = 10.0,
    relationship_type: str = "uncertain",
    analytical_comparability: str = "requires_review",
) -> GeographicMappingDecisionRow:
    """Create source-complete GIS evidence without using election-result data."""

    accepted = analytical_comparability == "accepted_direct"
    return GeographicMappingDecisionRow(
        mapping_id=mapping_id,
        previous_election_id="historical-surrey-county-council-divisions-2013-2021",
        previous_area_id=previous_id,
        previous_area_name=f"Historic {previous_id}",
        current_election_id="surrey-county-council-2026-east-surrey",
        current_area_id=current_id,
        current_area_name=f"Ward {current_id}",
        overlap_area_m2=100.0,
        previous_area_overlap_percentage=previous_overlap,
        current_area_overlap_percentage=current_overlap,
        largest_previous_area_competitor_percentage=0.0,
        largest_current_area_competitor_percentage=0.0,
        geometry_valid=True,
        boundary_sources_consistent=True,
        relationship_type=relationship_type,
        administrative_identity="not_confirmed",
        analytical_comparability=analytical_comparability,
        confidence="high" if accepted else "low",
        decision="accepted" if accepted else "requires_review",
        GIS_source="https://example.test/official-gis",
        boundary_source="https://example.test/boundary-order",
        evidence_notes="Mock GIS evidence.",
        reviewer_reason="Mock decision reason.",
        evidence_summary="Mock evidence summary.",
    )


def test_split_relationship_never_becomes_direct_mapping() -> None:
    """A historical area with two material targets is retained only as a crosswalk."""

    policy = load_geographic_crosswalk_resolution_policy()
    rows = build_geographic_crosswalk_resolution(
        (
            _decision_row("split:1", current_id="W1"),
            _decision_row("split:2", current_id="W2"),
        ),
        policy,
    )

    assert {row.analytical_status for row in rows} == {"partial_crosswalk_available"}
    assert {row.crosswalk_relationship_type for row in rows} == {"one_to_many"}
    assert direct_mappings_for_future_approved_use(rows) == ()


def test_merged_relationship_never_becomes_direct_mapping() -> None:
    """A current ward with two material historic sources is never one-to-one."""

    policy = load_geographic_crosswalk_resolution_policy()
    rows = build_geographic_crosswalk_resolution(
        (
            _decision_row("merged:1", previous_id="H1"),
            _decision_row("merged:2", previous_id="H2"),
        ),
        policy,
    )

    assert {row.analytical_status for row in rows} == {"partial_crosswalk_available"}
    assert {row.crosswalk_relationship_type for row in rows} == {"many_to_one"}
    assert direct_mappings_for_future_approved_use(rows) == ()


def test_crosswalk_preserves_many_to_many_topology() -> None:
    """Every edge in a two-by-two structural component remains in one audit component."""

    policy = load_geographic_crosswalk_resolution_policy()
    decisions = (
        _decision_row("many:1", previous_id="H1", current_id="W1"),
        _decision_row("many:2", previous_id="H1", current_id="W2"),
        _decision_row("many:3", previous_id="H2", current_id="W1"),
        _decision_row("many:4", previous_id="H2", current_id="W2"),
    )
    rows = build_geographic_crosswalk_resolution(decisions, policy)

    assert {row.crosswalk_relationship_type for row in rows} == {"many_to_many"}
    assert len({row.crosswalk_component_id for row in rows}) == 1
    assert {row.mapping_id for row in rows} == {row.mapping_id for row in decisions}


def test_crosswalk_does_not_invent_weights_or_allow_candidate_history() -> None:
    """GIS area ratios remain evidence and cannot become electoral redistribution weights."""

    policy = load_geographic_crosswalk_resolution_policy()
    rows = build_geographic_crosswalk_resolution(
        (
            _decision_row("split:1", current_id="W1"),
            _decision_row("split:2", current_id="W2"),
        ),
        policy,
    )

    for row in rows:
        assert row.weight_availability == "unavailable"
        assert row.weight_type is None
        assert row.weight_recommendation == "not_recommended"
        assert row.candidate_history_allowed is False
        assert row.incumbency_allowed is False
        assert row.previous_winner_allowed is False


def test_not_comparable_low_overlap_relationship_remains_blocked() -> None:
    """A small isolated fragment is not promoted to a partial crosswalk."""

    policy = load_geographic_crosswalk_resolution_policy()
    row = build_geographic_crosswalk_resolution(
        (_decision_row("fragment:1", previous_overlap=1.0, current_overlap=1.0),),
        policy,
    )[0]

    assert row.analytical_status == "not_comparable"
    assert row.allowed_future_use == "blocked_from_historical_analysis"
    assert row.crosswalk_component_id is None


def test_invalid_geometry_is_classified_for_source_remediation() -> None:
    """A geometry problem is not hidden as a low-overlap or partial relationship."""

    policy = load_geographic_crosswalk_resolution_policy()
    invalid = _decision_row("invalid:1", previous_overlap=1.0, current_overlap=1.0)
    invalid = GeographicMappingDecisionRow(
        **{**asdict(invalid), "geometry_valid": False}
    )
    row = build_geographic_crosswalk_resolution((invalid,), policy)[0]

    assert row.analytical_status == "requires_review"
    assert row.resolution_reason_code == "geometry_validation_failure"
    assert row.allowed_future_use == "blocked_pending_source_remediation"


def test_all_rows_remain_traceable_without_mutating_source_decisions() -> None:
    """Resolution partitions every row and leaves immutable decision evidence unchanged."""

    policy = load_geographic_crosswalk_resolution_policy()
    decisions = (
        _decision_row("direct:1", previous_overlap=99.95, current_overlap=99.95, relationship_type="near_exact", analytical_comparability="accepted_direct"),
        _decision_row("partial:1", previous_id="H2", current_id="W2"),
        _decision_row("partial:2", previous_id="H2", current_id="W3"),
        _decision_row("blocked:1", previous_id="H3", current_id="W4", previous_overlap=1.0, current_overlap=1.0),
    )
    before = tuple(asdict(row) for row in decisions)
    rows = build_geographic_crosswalk_resolution(decisions, policy)
    dataset = geographic_crosswalk_resolution_dataset(rows, policy)

    assert tuple(asdict(row) for row in decisions) == before
    assert len(dataset["resolution_rows"]) == len(decisions)
    assert {
        row["mapping_id"] for row in dataset["resolution_rows"]
    } == {row.mapping_id for row in decisions}
    assert len(dataset["final_direct_mapping_dataset"]) == 1
    assert len(dataset["analytical_crosswalk_dataset"]) == 2
    assert len(dataset["not_comparable_dataset"]) == 1
