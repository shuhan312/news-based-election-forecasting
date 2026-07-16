"""Tests for evidence-gated geographic mapping decisions."""

from __future__ import annotations

import pytest

from election_extractor.geographic_mapping_decision import (
    GeographicMappingReviewRow,
    ManualMappingDecision,
    approved_mappings_for_future_enrichment,
    build_geographic_mapping_decisions,
    geographic_mapping_decision_dataset,
    load_mapping_decision_policy,
)


def _review_row(mapping_type: str = "exact") -> GeographicMappingReviewRow:
    """Create a GIS review row without claiming it has legal equivalence evidence."""

    return GeographicMappingReviewRow(
        mapping_id="geographic-mapping-review:001",
        previous_election="historical-surrey-county-council-divisions-2013-2021",
        previous_area_id="H1",
        previous_area_name="Historical Division",
        current_election="surrey-county-council-2026-east-surrey",
        current_area_id="W1",
        current_area_name="2026 Ward",
        overlap_area_m2=100.0,
        previous_area_overlap_percentage=100.0,
        current_area_overlap_percentage=100.0,
        mapping_type=mapping_type,
        decision="requires_review",
        confidence="high",
        gis_source="https://example.test/official-gis",
        legal_boundary_source="https://example.test/2026-order",
        notes="GIS candidate only.",
    )


def test_unresolved_gis_row_remains_excluded_from_final_mapping() -> None:
    """A GIS exact classification does not create a final row by itself."""

    policy = load_mapping_decision_policy()
    decisions = build_geographic_mapping_decisions((_review_row(),), policy)

    assert decisions[0].decision == "requires_review"
    assert decisions[0].confidence == "low"
    assert approved_mappings_for_future_enrichment(decisions) == ()


def test_accepted_mapping_requires_direct_boundary_evidence() -> None:
    """Manual acceptance without pair-specific legal evidence is rejected."""

    policy = load_mapping_decision_policy()
    manual = ManualMappingDecision(
        mapping_id="geographic-mapping-review:001",
        decision="accepted",
        confidence="high",
        reviewer_reason="Reviewer considers the areas equivalent.",
    )

    with pytest.raises(ValueError, match="direct_boundary_evidence"):
        build_geographic_mapping_decisions((_review_row(),), policy, (manual,))


def test_evidence_complete_exact_mapping_can_be_exposed_to_future_enrichment() -> None:
    """Only an explicit, evidence-complete future approval can pass the guard."""

    policy = load_mapping_decision_policy()
    manual = ManualMappingDecision(
        mapping_id="geographic-mapping-review:001",
        decision="accepted",
        confidence="high",
        reviewer_reason="Official order directly confirms the pair's equivalence.",
        direct_boundary_evidence="https://example.test/direct-official-crosswalk",
        evidence_summary="Article X explicitly links Historical Division and 2026 Ward.",
    )
    decisions = build_geographic_mapping_decisions((_review_row(),), policy, (manual,))
    approved = approved_mappings_for_future_enrichment(decisions)

    assert len(approved) == 1
    assert approved[0]["decision"] == "accepted"
    assert approved[0]["boundary_source"] == "https://example.test/direct-official-crosswalk"


@pytest.mark.parametrize("mapping_type", ["split", "merged"])
def test_split_and_merged_rows_cannot_be_accepted_for_future_enrichment(
    mapping_type: str,
) -> None:
    """Multi-area relationships cannot become a one-to-one analytical bridge."""

    policy = load_mapping_decision_policy()
    manual = ManualMappingDecision(
        mapping_id="geographic-mapping-review:001",
        decision="accepted",
        confidence="high",
        reviewer_reason="Attempted manual acceptance.",
        direct_boundary_evidence="https://example.test/direct-crosswalk",
        evidence_summary="Purported direct evidence.",
    )

    with pytest.raises(ValueError, match="Only exact or near_exact"):
        build_geographic_mapping_decisions((_review_row(mapping_type),), policy, (manual,))


def test_decision_dataset_retains_methodology_and_creates_no_automatic_mapping() -> None:
    """The report documents restrictions instead of generating electoral features."""

    policy = load_mapping_decision_policy()
    decisions = build_geographic_mapping_decisions((_review_row("uncertain"),), policy)
    dataset = geographic_mapping_decision_dataset(decisions, policy)

    assert dataset["summary"]["final_geographic_mapping_rows"] == 0
    assert dataset["summary"]["historical_features_generated"] is False
    assert dataset["methodology"]["prohibited_actions"]
