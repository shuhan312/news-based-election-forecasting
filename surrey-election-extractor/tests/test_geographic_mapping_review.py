"""Tests for the review-only GIS-to-geographic-mapping bridge."""

from __future__ import annotations

from copy import deepcopy

import pytest

from election_extractor.geographic_mapping_review import (
    build_geographic_mapping_review,
    geographic_mapping_review_dataset,
    geographic_mapping_review_summary,
)


def _candidate(
    previous_id: str,
    current_id: str,
    *,
    previous_overlap: float,
    current_overlap: float,
) -> dict[str, object]:
    """Create one source-complete overlap candidate for review tests."""

    return {
        "previous_area_id": previous_id,
        "previous_area_name": f"Historic {previous_id}",
        "current_election_id": "surrey-county-council-2026-east-surrey",
        "current_area_id": current_id,
        "current_area_name": f"Current {current_id}",
        "intersection_area_square_metres": 100.0,
        "previous_area_overlap_percent": previous_overlap,
        "current_area_overlap_percent": current_overlap,
        "previous_geometry_source_url": "https://example.test/historic-gis",
        "current_geometry_source_url": "https://example.test/current-gis",
        "previous_geometry_valid": True,
        "current_geometry_valid": True,
    }


def _overlap_audit() -> dict[str, object]:
    """Provide exact, split, merged and uncertain relationships together."""

    return {
        "candidate_overlap_rows": [
            _candidate("H1", "W1", previous_overlap=100.0, current_overlap=100.0),
            _candidate("H2", "W2", previous_overlap=60.0, current_overlap=60.0),
            _candidate("H2", "W3", previous_overlap=40.0, current_overlap=40.0),
            _candidate("H3", "W4", previous_overlap=50.0, current_overlap=60.0),
            _candidate("H4", "W4", previous_overlap=50.0, current_overlap=40.0),
            _candidate("H5", "W5", previous_overlap=20.0, current_overlap=20.0),
        ],
        "legal_2026_source": {
            "source_url": "https://example.test/official-order",
            "evidence_text": "Official legal boundary evidence.",
        },
    }


def test_every_candidate_is_retained_but_none_is_automatically_accepted() -> None:
    """GIS classification cannot turn an overlap candidate into a final map."""

    rows = build_geographic_mapping_review(_overlap_audit())

    assert len(rows) == 6
    assert all(row.decision == "requires_review" for row in rows)
    assert {row.mapping_type for row in rows} == {"exact", "split", "merged", "uncertain"}
    assert all(row.gis_source.startswith("https://") for row in rows)
    assert all(row.legal_boundary_source.startswith("https://") for row in rows)


def test_uncertain_relationships_remain_unresolved() -> None:
    """Weak and many-to-many GIS relationships must not be treated as equivalent."""

    rows = build_geographic_mapping_review(_overlap_audit())
    uncertain = [row for row in rows if row.mapping_type == "uncertain"]

    assert uncertain
    assert all(row.decision == "requires_review" for row in uncertain)
    assert all(row.confidence == "low" for row in uncertain)


def test_split_and_merged_relationships_are_explicitly_flagged() -> None:
    """One-to-many and many-to-one cases cannot become one-to-one mappings."""

    rows = {row.mapping_id: row for row in build_geographic_mapping_review(_overlap_audit())}

    assert rows["geographic-mapping-review:002"].mapping_type == "split"
    assert rows["geographic-mapping-review:003"].mapping_type == "split"
    assert rows["geographic-mapping-review:004"].mapping_type == "merged"
    assert rows["geographic-mapping-review:005"].mapping_type == "merged"


def test_tiny_extra_candidate_does_not_create_a_false_split() -> None:
    """A shared-edge candidate stays visible but is not a structural split."""

    audit = _overlap_audit()
    candidates = audit["candidate_overlap_rows"]
    assert isinstance(candidates, list)
    candidates.append(_candidate("H1", "W6", previous_overlap=0.02, current_overlap=0.02))

    rows = build_geographic_mapping_review(audit)

    assert rows[0].mapping_type == "exact"
    assert rows[-1].mapping_type == "uncertain"


def test_review_dataset_creates_no_final_mapping_or_historical_features() -> None:
    """The review output is not a path to automatic electoral comparison."""

    rows = build_geographic_mapping_review(_overlap_audit())
    summary = geographic_mapping_review_summary(rows)
    dataset = geographic_mapping_review_dataset(rows, summary)

    assert summary["accepted_mappings"] == 0
    assert summary["final_geographic_mapping_rows_created"] == 0
    assert summary["historical_features_generated"] is False
    assert dataset["methodology"]["prohibited_actions"]


def test_missing_evidence_rejects_a_review_row() -> None:
    """A candidate cannot enter review without the documented source evidence."""

    audit = deepcopy(_overlap_audit())
    candidates = audit["candidate_overlap_rows"]
    assert isinstance(candidates, list)
    first = candidates[0]
    assert isinstance(first, dict)
    first.pop("previous_geometry_source_url")

    with pytest.raises(ValueError, match="previous GIS source"):
        build_geographic_mapping_review(audit)
