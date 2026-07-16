"""Tests for strict analytical decisions from the GIS review dataset."""

from __future__ import annotations

from election_extractor.geographic_mapping_decision import (
    approved_mappings_for_future_enrichment,
    build_geographic_mapping_decisions,
    geographic_mapping_decision_dataset,
    load_mapping_decision_policy,
)
from election_extractor.geographic_mapping_review import GeographicMappingReviewRow


def _review_row(
    mapping_id: str,
    *,
    mapping_type: str = "near_exact",
    previous_id: str = "H1",
    current_id: str = "W1",
    previous_overlap: float = 99.95,
    current_overlap: float = 99.96,
    geometry_valid: bool = True,
    sources_consistent: bool = True,
) -> GeographicMappingReviewRow:
    """Create a source-complete candidate without using an area name as evidence."""

    return GeographicMappingReviewRow(
        mapping_id=mapping_id,
        previous_election="historical-surrey-county-council-divisions-2013-2021",
        previous_area_id=previous_id,
        previous_area_name="Same-looking name is not used",
        current_election="surrey-county-council-2026-east-surrey",
        current_area_id=current_id,
        current_area_name="Completely different published name",
        overlap_area_m2=100.0,
        previous_area_overlap_percentage=previous_overlap,
        current_area_overlap_percentage=current_overlap,
        mapping_type=mapping_type,
        decision="requires_review",
        confidence="high",
        gis_source="https://example.test/official-gis",
        legal_boundary_source="https://example.test/2026-order",
        geometry_valid=geometry_valid,
        boundary_sources_consistent=sources_consistent,
        notes="GIS candidate only.",
    )


def test_administrative_identity_and_analytical_comparability_are_separate() -> None:
    """A strict GIS match may be analytically accepted without a legal identity claim."""

    policy = load_mapping_decision_policy()
    decisions = build_geographic_mapping_decisions((_review_row("review:1"),), policy)
    decision = decisions[0]

    assert decision.administrative_identity == "not_confirmed"
    assert decision.analytical_comparability == "accepted_direct"
    assert decision.decision == "accepted"


def test_strong_gis_evidence_creates_accepted_direct_without_name_matching() -> None:
    """The test deliberately uses different names to prove names are not a criterion."""

    policy = load_mapping_decision_policy()
    decisions = build_geographic_mapping_decisions((_review_row("review:1"),), policy)
    approved = approved_mappings_for_future_enrichment(decisions)

    assert len(approved) == 1
    assert approved[0]["analytical_comparability"] == "accepted_direct"
    assert approved[0]["administrative_identity"] == "not_confirmed"


def test_split_merged_and_uncertain_rows_cannot_be_direct_mappings() -> None:
    """Multi-area and uncertain relationships remain outside downstream input."""

    policy = load_mapping_decision_policy()
    rows = (
        _review_row("review:split", mapping_type="split"),
        _review_row("review:merged", mapping_type="merged", previous_id="H2", current_id="W2"),
        _review_row("review:uncertain", mapping_type="uncertain", previous_id="H3", current_id="W3"),
    )
    decisions = build_geographic_mapping_decisions(rows, policy)

    assert approved_mappings_for_future_enrichment(decisions) == ()
    assert {row.analytical_comparability for row in decisions} == {
        "not_comparable",
        "requires_review",
    }


def test_invalid_geometry_cannot_be_accepted_direct() -> None:
    """A geometry-validation failure is an explicit direct-criteria failure."""

    policy = load_mapping_decision_policy()
    invalid = _review_row("review:invalid", geometry_valid=False)
    decision = build_geographic_mapping_decisions((invalid,), policy)[0]

    assert decision.decision == "requires_review"
    assert decision.analytical_comparability == "requires_review"
    assert "invalid" in decision.reviewer_reason


def test_significant_competitor_prevents_one_to_one_acceptance() -> None:
    """Largest overlap is insufficient where another relationship is significant."""

    policy = load_mapping_decision_policy()
    primary = _review_row("review:primary", previous_overlap=99.95, current_overlap=99.95)
    competing = _review_row(
        "review:competing",
        previous_id="H1",
        current_id="W2",
        previous_overlap=0.2,
        current_overlap=0.2,
        mapping_type="uncertain",
    )
    decision = build_geographic_mapping_decisions((primary, competing), policy)[0]

    assert decision.analytical_comparability == "requires_review"
    assert "competing overlap" in decision.reviewer_reason


def test_all_review_rows_remain_traceable_in_decision_dataset() -> None:
    """The decision layer retains every candidate even when only one is accepted."""

    policy = load_mapping_decision_policy()
    rows = (
        _review_row("review:accepted"),
        _review_row("review:unresolved", previous_id="H2", current_id="W2", previous_overlap=90, current_overlap=90),
    )
    decisions = build_geographic_mapping_decisions(rows, policy)
    dataset = geographic_mapping_decision_dataset(decisions, policy)

    assert len(dataset["decision_rows"]) == 2
    assert dataset["summary"]["accepted_direct_mappings"] == 1
    assert dataset["summary"]["requires_review_mappings"] == 1
    assert dataset["approved_direct_mappings"][0]["mapping_id"] == "review:accepted"
    assert dataset["unresolved_mappings"][0]["mapping_id"] == "review:unresolved"
