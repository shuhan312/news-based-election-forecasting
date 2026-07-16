"""Create a review dataset from GIS overlap candidates without approving maps.

Spatial overlap is evidence, not proof of comparable electoral geography.  This
module makes every classification and review decision visible while ensuring
that no candidate can populate the master ``Geographic Mapping`` table or
create historical electoral features.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any


EXACT_MUTUAL_OVERLAP_PERCENT = 99.999
NEAR_EXACT_MUTUAL_OVERLAP_PERCENT = 95.0
# A relationship is structurally split or merged only if it covers a material
# part of both areas. This avoids treating a small shared-edge fragment as a
# substantive change to an otherwise one-to-one geography.
STRUCTURAL_RELATIONSHIP_PERCENT = 5.0


@dataclass(frozen=True)
class GeographicMappingReviewRow:
    """One review-only row with source evidence and a provisional classification."""

    mapping_id: str
    previous_election: str
    previous_area_id: str
    previous_area_name: str
    current_election: str
    current_area_id: str
    current_area_name: str
    overlap_area_m2: float
    previous_area_overlap_percentage: float
    current_area_overlap_percentage: float
    mapping_type: str
    decision: str
    confidence: str
    gis_source: str
    legal_boundary_source: str
    notes: str


def _required_text(value: object, field_name: str) -> str:
    """Require published evidence values instead of manufacturing a fallback."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Geographic mapping review requires non-empty {field_name}.")
    return value.strip()


def _required_number(value: object, field_name: str) -> float:
    """Reject malformed overlap evidence rather than classifying it anyway."""

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Geographic mapping review requires numeric {field_name}.")
    return float(value)


def _candidate_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    """Identify one source-preserving overlap relationship deterministically."""

    return (
        _required_text(row.get("previous_area_id"), "previous_area_id"),
        _required_text(row.get("current_election_id"), "current_election_id"),
        _required_text(row.get("current_area_id"), "current_area_id"),
    )


def _mapping_type(
    *,
    historical_relationship_count: int,
    current_relationship_count: int,
    previous_overlap_percentage: float,
    current_overlap_percentage: float,
    relationship_is_structural: bool,
) -> tuple[str, str]:
    """Classify relationship structure without converting it into approval.

    One-to-many and many-to-one cases take priority only when the additional
    links are structurally material. Even exact-looking one-to-one pairs remain
    ``requires_review`` because GIS must be read with legal source evidence.
    """

    minimum_overlap = min(previous_overlap_percentage, current_overlap_percentage)
    if (
        relationship_is_structural
        and historical_relationship_count > 1
        and current_relationship_count > 1
    ):
        return (
            "uncertain",
            "Both areas have multiple material GIS relationships; this is a many-to-many boundary change.",
        )
    if relationship_is_structural and historical_relationship_count > 1:
        return (
            "split",
            "The historical division has multiple material 2026 ward overlaps; it is not one-to-one.",
        )
    if relationship_is_structural and current_relationship_count > 1:
        return (
            "merged",
            "The 2026 ward has multiple material historical-division overlaps; it is not one-to-one.",
        )
    if minimum_overlap >= EXACT_MUTUAL_OVERLAP_PERCENT:
        return (
            "exact",
            "One-to-one GIS relationship with near-total mutual area coverage; legal review is still required before approval.",
        )
    if minimum_overlap >= NEAR_EXACT_MUTUAL_OVERLAP_PERCENT:
        return (
            "near_exact",
            "One-to-one GIS relationship with high mutual area coverage, but a boundary difference remains.",
        )
    return (
        "uncertain",
        "Material GIS overlap exists, but it is not sufficient to establish a comparable one-to-one geography.",
    )


def _confidence(mapping_type: str) -> str:
    """Describe evidence strength, not approval or analytical comparability."""

    if mapping_type == "exact":
        return "high"
    if mapping_type == "near_exact":
        return "medium"
    return "low"


def build_geographic_mapping_review(
    overlap_audit: Mapping[str, object],
) -> tuple[GeographicMappingReviewRow, ...]:
    """Classify every material candidate and leave every decision unresolved.

    The spatial-audit generator already filters out non-material boundary
    contacts using its documented threshold.  This function does not remove,
    rank or select any remaining candidate.  It produces one review record per
    candidate and sets ``decision`` to ``requires_review`` for all of them.
    """

    raw_rows = overlap_audit.get("candidate_overlap_rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("Geographic mapping review requires candidate_overlap_rows.")
    legal_source = overlap_audit.get("legal_2026_source")
    if not isinstance(legal_source, Mapping):
        raise ValueError("Geographic mapping review requires legal_2026_source.")
    legal_source_url = _required_text(legal_source.get("source_url"), "legal source URL")
    legal_evidence = _required_text(legal_source.get("evidence_text"), "legal evidence text")

    candidates: list[Mapping[str, object]] = []
    keys: set[tuple[str, str, str]] = set()
    for row in raw_rows:
        if not isinstance(row, Mapping):
            raise ValueError("Geographic mapping review candidates must be objects.")
        key = _candidate_key(row)
        if key in keys:
            raise ValueError("Geographic mapping review has duplicate GIS candidates.")
        keys.add(key)
        candidates.append(row)

    # The low GIS threshold keeps all potential evidence visible. Structural
    # counts use a stricter threshold solely for split/merged classification;
    # they never accept, reject or remove a review candidate.
    structural_candidates = [
        row
        for row in candidates
        if min(
            _required_number(
                row.get("previous_area_overlap_percent"),
                "previous_area_overlap_percent",
            ),
            _required_number(
                row.get("current_area_overlap_percent"),
                "current_area_overlap_percent",
            ),
        ) >= STRUCTURAL_RELATIONSHIP_PERCENT
    ]
    historical_counts = Counter(
        _required_text(row.get("previous_area_id"), "previous_area_id")
        for row in structural_candidates
    )
    current_counts = Counter(
        (
            _required_text(row.get("current_election_id"), "current_election_id"),
            _required_text(row.get("current_area_id"), "current_area_id"),
        )
        for row in structural_candidates
    )
    reviewed = []
    for index, row in enumerate(candidates, start=1):
        previous_id, current_election, current_id = _candidate_key(row)
        previous_overlap = _required_number(
            row.get("previous_area_overlap_percent"),
            "previous_area_overlap_percent",
        )
        current_overlap = _required_number(
            row.get("current_area_overlap_percent"),
            "current_area_overlap_percent",
        )
        mapping_type, reason = _mapping_type(
            historical_relationship_count=historical_counts[previous_id],
            current_relationship_count=current_counts[(current_election, current_id)],
            previous_overlap_percentage=previous_overlap,
            current_overlap_percentage=current_overlap,
            relationship_is_structural=(
                min(previous_overlap, current_overlap) >= STRUCTURAL_RELATIONSHIP_PERCENT
            ),
        )
        gis_source = "; ".join(
            (
                _required_text(row.get("previous_geometry_source_url"), "previous GIS source"),
                _required_text(row.get("current_geometry_source_url"), "current GIS source"),
            )
        )
        reviewed.append(
            GeographicMappingReviewRow(
                mapping_id=f"geographic-mapping-review:{index:03d}",
                previous_election="historical-surrey-county-council-divisions-2013-2021",
                previous_area_id=previous_id,
                previous_area_name=_required_text(
                    row.get("previous_area_name"),
                    "previous_area_name",
                ),
                current_election=current_election,
                current_area_id=current_id,
                current_area_name=_required_text(row.get("current_area_name"), "current_area_name"),
                overlap_area_m2=_required_number(
                    row.get("intersection_area_square_metres"),
                    "intersection_area_square_metres",
                ),
                previous_area_overlap_percentage=previous_overlap,
                current_area_overlap_percentage=current_overlap,
                mapping_type=mapping_type,
                # Classification is not a decision.  Human and legal review is
                # mandatory before a separate later process can accept a pair.
                decision="requires_review",
                confidence=_confidence(mapping_type),
                gis_source=gis_source,
                legal_boundary_source=f"{legal_source_url} — {legal_evidence}",
                notes=reason,
            )
        )
    return tuple(reviewed)


def geographic_mapping_review_summary(
    rows: Sequence[GeographicMappingReviewRow],
) -> dict[str, object]:
    """Summarise provisional classifications without creating Geographic Mapping rows."""

    if not rows:
        raise ValueError("Geographic mapping review summary requires rows.")
    mapping_types = Counter(row.mapping_type for row in rows)
    decisions = Counter(row.decision for row in rows)
    split_or_merged = sum(row.mapping_type in {"split", "merged"} for row in rows)
    return {
        "total_overlaps_reviewed": len(rows),
        "accepted_mappings": decisions["accepted"],
        "rejected_mappings": decisions["rejected"],
        "requires_review_mappings": decisions["requires_review"],
        "classification_counts": dict(sorted(mapping_types.items())),
        "split_or_merged_cases": split_or_merged,
        "final_geographic_mapping_rows_created": 0,
        "historical_features_generated": False,
    }


def geographic_mapping_review_dataset(
    rows: Sequence[GeographicMappingReviewRow],
    summary: Mapping[str, object],
) -> dict[str, object]:
    """Package the review dataset and methodology in a JSON-ready structure."""

    return {
        "status": "review_framework_complete",
        "summary": dict(summary),
        "methodology": {
            "exact_threshold": EXACT_MUTUAL_OVERLAP_PERCENT,
            "near_exact_threshold": NEAR_EXACT_MUTUAL_OVERLAP_PERCENT,
            "structural_split_merged_threshold": STRUCTURAL_RELATIONSHIP_PERCENT,
            "acceptance_criteria": (
                "No GIS-only row is accepted. A later approval must preserve GIS "
                "evidence and direct official legal-boundary evidence for that pair."
            ),
            "decision_policy": "All GIS-only classifications remain requires_review.",
            "limitations": [
                "Spatial overlap does not prove comparable electorates or voting geography.",
                "Shared names and largest-overlap relationships are not equivalence evidence.",
                "No historical electoral feature is generated from this review dataset.",
            ],
            "prohibited_actions": [
                "Do not write Geographic Mapping rows from this dataset.",
                "Do not calculate vote change, previous winner, incumbency or candidate history.",
                "Do not treat a shared name or the largest overlap as evidence of equivalence.",
            ],
        },
        "review_rows": [asdict(row) for row in rows],
    }


def geographic_mapping_review_markdown(dataset: Mapping[str, Any]) -> str:
    """Render a concise report that makes unresolved status visible in prose."""

    summary = dataset["summary"]
    assert isinstance(summary, Mapping)
    classifications = summary["classification_counts"]
    assert isinstance(classifications, Mapping)
    rows = dataset["review_rows"]
    assert isinstance(rows, list)
    lines = [
        "# Surrey Geographic Mapping Review Report",
        "",
        "## Review outcome",
        "",
        f"- Total material GIS overlaps reviewed: {summary['total_overlaps_reviewed']}",
        f"- Accepted mappings: {summary['accepted_mappings']}",
        f"- Rejected mappings: {summary['rejected_mappings']}",
        f"- Requires-review mappings: {summary['requires_review_mappings']}",
        f"- Split or merged relationships: {summary['split_or_merged_cases']}",
        f"- Final Geographic Mapping rows created: {summary['final_geographic_mapping_rows_created']}",
        f"- Historical features generated: {summary['historical_features_generated']}",
        "",
        "## Classification counts",
        "",
    ]
    for mapping_type, count in classifications.items():
        lines.append(f"- {mapping_type}: {count}")
    lines.extend(
        [
            "",
            "## Methodology",
            "",
            "Each row is a material spatial-overlap candidate, not a final mapping. "
            "A candidate is classified as exact or near_exact only when it is one-to-one "
            "and meets the stated mutual-coverage threshold. One-to-many relationships "
            "are classified as split; many-to-one relationships as merged; many-to-many "
            "or weaker one-to-one relationships as uncertain.",
            "",
            "## Acceptance criteria and limitations",
            "",
            "No row is accepted by this report. A later decision requires both the retained "
            "GIS evidence and direct official legal boundary evidence for the individual pair. "
            "A shared name, the largest overlap, or spatial area alone is insufficient. "
            "The report also does not establish comparable electorates or voting geography.",
            "",
            "All decisions remain `requires_review`. GIS and legal boundary evidence are "
            "retained in every row, but no historical comparison is permitted until a future "
            "explicit approval process records a final mapping decision.",
            "",
            "## Review dataset",
            "",
            "| Mapping ID | Previous division | Current ward | Type | Decision | Confidence | Previous overlap | Current overlap |",
            "| --- | --- | --- | --- | --- | --- | ---: | ---: |",
        ]
    )
    for row in rows:
        assert isinstance(row, Mapping)
        lines.append(
            "| {mapping_id} | {previous_area_name} | {current_area_name} | {mapping_type} | "
            "{decision} | {confidence} | {previous_area_overlap_percentage:.3f}% | "
            "{current_area_overlap_percentage:.3f}% |".format(**row)
        )
    lines.extend(
        [
            "",
            "The full JSON review dataset retains overlap area, both GIS source URLs, "
            "the legal boundary source and the classification reasoning for every row.",
            "",
        ]
    )
    return "\n".join(lines)
