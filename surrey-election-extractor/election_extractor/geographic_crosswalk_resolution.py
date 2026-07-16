"""Resolve GIS relationships into direct, partial and blocked analytical outputs.

This module is deliberately a geographic evidence layer.  It reads the
existing 167 mapping decisions, preserves every relationship and never reads
or changes election-result records.  In particular, a partial crosswalk is a
description of boundary topology, not a method for redistributing votes.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from election_extractor.geographic_mapping_decision import GeographicMappingDecisionRow
from election_extractor.geographic_mapping_review import STRUCTURAL_RELATIONSHIP_PERCENT


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CROSSWALK_POLICY_PATH = (
    PROJECT_ROOT / "config/geographic_crosswalk_resolution_policy.json"
)
VALID_ANALYTICAL_STATUSES = frozenset(
    {
        "accepted_direct",
        "partial_crosswalk_available",
        "not_comparable",
        "requires_review",
    }
)


@dataclass(frozen=True)
class GeographicCrosswalkResolutionPolicy:
    """Store crosswalk thresholds and weight limits as reviewable configuration."""

    framework_id: str
    structural_overlap_percentage: float
    low_overlap_not_comparable_percentage: float
    weighting_assessment: Mapping[str, str]
    weighting_reason: str
    prohibited_actions: tuple[str, ...]


@dataclass(frozen=True)
class GeographicCrosswalkResolutionRow:
    """One traceable classification of a historical-to-2026 GIS relationship."""

    mapping_id: str
    previous_election_id: str
    previous_area_id: str
    previous_area_name: str
    current_election_id: str
    current_area_id: str
    current_area_name: str
    relationship_type: str
    crosswalk_relationship_type: str | None
    crosswalk_component_id: str | None
    intersection_area_m2: float
    source_overlap_ratio: float
    target_overlap_ratio: float
    GIS_source: str
    boundary_source: str
    analytical_status: str
    resolution_reason_code: str
    decision_reason: str
    evidence_summary: str
    confidence: str
    uncertainty: str
    weight_availability: str
    weight_type: str | None
    weight_recommendation: str
    allowed_future_use: str
    candidate_history_allowed: bool
    incumbency_allowed: bool
    previous_winner_allowed: bool


def _required_text(value: object, field_name: str) -> str:
    """Reject missing policy text rather than silently supplying a fallback."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Geographic crosswalk resolution requires non-empty {field_name}.")
    return value.strip()


def _required_number(value: object, field_name: str) -> float:
    """Require a numeric threshold so no classification uses an implicit value."""

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Geographic crosswalk resolution requires numeric {field_name}.")
    return float(value)


def load_geographic_crosswalk_resolution_policy(
    path: str | Path = DEFAULT_CROSSWALK_POLICY_PATH,
) -> GeographicCrosswalkResolutionPolicy:
    """Load documented topology and weighting constraints without election data."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Geographic crosswalk resolution policy must be an object.")
    structural = _required_number(
        payload.get("structural_overlap_percentage"),
        "structural_overlap_percentage",
    )
    low_overlap = _required_number(
        payload.get("low_overlap_not_comparable_percentage"),
        "low_overlap_not_comparable_percentage",
    )
    if structural != STRUCTURAL_RELATIONSHIP_PERCENT or low_overlap != structural:
        raise ValueError(
            "Crosswalk policy must use the existing documented structural GIS threshold."
        )
    raw_weighting = payload.get("weighting_assessment")
    if not isinstance(raw_weighting, Mapping):
        raise ValueError("Crosswalk policy requires weighting_assessment.")
    required_weight_types = {
        "electorate_weighted",
        "population_weighted",
        "residential_weighted",
        "area_weighted",
    }
    if set(raw_weighting) != required_weight_types | {"reason"}:
        raise ValueError("Crosswalk policy must document every considered weighting type.")
    weighting_assessment = {
        key: _required_text(raw_weighting.get(key), key)
        for key in sorted(required_weight_types)
    }
    if any(value == "available" for value in weighting_assessment.values()):
        raise ValueError("No weighting source may be treated as available without a separate audit.")
    prohibited = payload.get("prohibited_actions")
    if not isinstance(prohibited, list) or not prohibited:
        raise ValueError("Crosswalk policy requires prohibited_actions.")
    return GeographicCrosswalkResolutionPolicy(
        framework_id=_required_text(payload.get("framework_id"), "framework_id"),
        structural_overlap_percentage=structural,
        low_overlap_not_comparable_percentage=low_overlap,
        weighting_assessment=weighting_assessment,
        weighting_reason=_required_text(raw_weighting.get("reason"), "weighting reason"),
        prohibited_actions=tuple(_required_text(item, "prohibited action") for item in prohibited),
    )


def _mutual_overlap(row: GeographicMappingDecisionRow) -> float:
    """Use the smaller directional overlap as the conservative relationship measure."""

    return min(row.previous_area_overlap_percentage, row.current_area_overlap_percentage)


def _structural_counts(
    rows: Sequence[GeographicMappingDecisionRow],
    threshold: float,
) -> tuple[Counter[str], Counter[tuple[str, str]]]:
    """Count material links without using them to create a direct mapping."""

    material_rows = [row for row in rows if _mutual_overlap(row) >= threshold]
    return (
        Counter(row.previous_area_id for row in material_rows),
        Counter(
            (row.current_election_id, row.current_area_id)
            for row in material_rows
        ),
    )


def _is_partial_component(
    row: GeographicMappingDecisionRow,
    previous_counts: Mapping[str, int],
    current_counts: Mapping[tuple[str, str], int],
) -> bool:
    """Retain every edge attached to a material split, merge or many-to-many component."""

    return (
        previous_counts[row.previous_area_id] > 1
        or current_counts[(row.current_election_id, row.current_area_id)] > 1
    )


def _component_identifiers(
    partial_rows: Sequence[GeographicMappingDecisionRow],
) -> dict[str, str]:
    """Assign stable IDs to connected many-to-many topology components.

    The component ID is an audit label only.  It does not combine results or
    imply that all areas in the component are politically comparable.
    """

    neighbours: defaultdict[tuple[str, ...], set[tuple[str, ...]]] = defaultdict(set)
    row_nodes: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for row in partial_rows:
        previous_node = ("previous", row.previous_area_id)
        current_node = ("current", row.current_election_id, row.current_area_id)
        neighbours[previous_node].add(current_node)
        neighbours[current_node].add(previous_node)
        row_nodes[row.mapping_id] = (previous_node, current_node)

    node_components: dict[tuple[str, ...], str] = {}
    component_index = 0
    for starting_node in sorted(neighbours):
        if starting_node in node_components:
            continue
        component_index += 1
        component_id = f"crosswalk-component:{component_index:03d}"
        pending = [starting_node]
        node_components[starting_node] = component_id
        while pending:
            node = pending.pop()
            for neighbour in sorted(neighbours[node]):
                if neighbour not in node_components:
                    node_components[neighbour] = component_id
                    pending.append(neighbour)
    return {
        mapping_id: node_components[nodes[0]]
        for mapping_id, nodes in row_nodes.items()
    }


def _crosswalk_relationship_type(
    row: GeographicMappingDecisionRow,
    previous_counts: Mapping[str, int],
    current_counts: Mapping[tuple[str, str], int],
) -> str:
    """Describe topology while preserving one-to-many and many-to-many direction."""

    previous_multiple = previous_counts[row.previous_area_id] > 1
    current_multiple = current_counts[(row.current_election_id, row.current_area_id)] > 1
    if previous_multiple and current_multiple:
        return "many_to_many"
    if previous_multiple:
        return "one_to_many"
    if current_multiple:
        return "many_to_one"
    raise ValueError("Crosswalk relationship type requires a structural component.")


def _partial_reason(
    row: GeographicMappingDecisionRow,
    relationship_type: str,
    threshold: float,
) -> str:
    """Explain why GIS topology is retained but not used as an electoral bridge."""

    if _mutual_overlap(row) < threshold:
        return (
            "Non-material edge retained because it belongs to a material "
            f"{relationship_type} boundary component; it cannot become a direct mapping."
        )
    return (
        f"Material {relationship_type} boundary relationship at the documented "
        f"{threshold:.1f}% structural threshold; preserve as a partial crosswalk only."
    )


def _resolution_fields(
    *,
    row: GeographicMappingDecisionRow,
    partial: bool,
    policy: GeographicCrosswalkResolutionPolicy,
) -> tuple[
    str,
    str,
    str,
    str,
    str | None,
    str,
    str,
    str,
    str,
    bool,
    bool,
    bool,
]:
    """Return only non-electoral permissions for a classified relationship."""

    if row.analytical_comparability == "accepted_direct":
        return (
            "accepted_direct",
            "high",
            "low",
            "not_applicable",
            None,
            "not_applicable",
            "eligible_for_future_direct_analysis_only_after_explicit_approval",
            "accepted_direct_criteria_pass",
            "Strict one-to-one direct GIS criteria were already accepted.",
            False,
            False,
            False,
        )
    if partial:
        return (
            "partial_crosswalk_available",
            "medium",
            "high",
            "unavailable",
            None,
            "not_recommended",
            "aggregate_crosswalk_review_only; all electoral and candidate features remain blocked",
            "structural_partial_crosswalk",
            policy.weighting_reason,
            False,
            False,
            False,
        )
    if _mutual_overlap(row) < policy.low_overlap_not_comparable_percentage:
        return (
            "not_comparable",
            "high",
            "low",
            "unavailable",
            None,
            "not_recommended",
            "blocked_from_historical_analysis",
            "non_structural_insufficient_overlap",
            "Non-structural low-overlap fragment has no analytical crosswalk use.",
            False,
            False,
            False,
        )
    return (
        "requires_review",
        "low",
        "medium",
        "unavailable",
        None,
        "not_recommended",
        "blocked_pending_boundary_version_or_competitor_review",
        "one_to_one_direct_criteria_unmet",
        "One-to-one candidate is not direct: further boundary-version or competing-area review is required.",
        False,
        False,
        False,
    )


def build_geographic_crosswalk_resolution(
    decisions: Sequence[GeographicMappingDecisionRow],
    policy: GeographicCrosswalkResolutionPolicy,
) -> tuple[GeographicCrosswalkResolutionRow, ...]:
    """Classify all decision rows without changing the existing direct decisions."""

    if not decisions:
        raise ValueError("Geographic crosswalk resolution requires decision rows.")
    if len({row.mapping_id for row in decisions}) != len(decisions):
        raise ValueError("Geographic crosswalk resolution requires unique mapping IDs.")
    previous_counts, current_counts = _structural_counts(
        decisions,
        policy.structural_overlap_percentage,
    )
    partial_rows = tuple(
        row
        for row in decisions
        if row.analytical_comparability != "accepted_direct"
        and _is_partial_component(row, previous_counts, current_counts)
    )
    component_ids = _component_identifiers(partial_rows)
    resolved = []
    for row in decisions:
        partial = row.mapping_id in component_ids
        # Invalid geometry or inconsistent sources are never hidden inside a
        # topology classification. They require source remediation first.
        source_problem = not row.geometry_valid or not row.boundary_sources_consistent
        (
            status,
            confidence,
            uncertainty,
            weight_availability,
            weight_type,
            weight_recommendation,
            allowed_future_use,
            reason_code,
            policy_reason,
            candidate_history_allowed,
            incumbency_allowed,
            previous_winner_allowed,
        ) = _resolution_fields(
            row=row,
            partial=partial and not source_problem,
            policy=policy,
        )
        if source_problem and row.analytical_comparability != "accepted_direct":
            status = "requires_review"
            confidence = "low"
            uncertainty = "high"
            weight_availability = "unavailable"
            weight_type = None
            weight_recommendation = "not_recommended"
            allowed_future_use = "blocked_pending_source_remediation"
            reason_code = (
                "geometry_validation_failure"
                if not row.geometry_valid
                else "boundary_source_inconsistency"
            )
            policy_reason = (
                "Source geometry is invalid."
                if not row.geometry_valid
                else "Configured boundary sources are not consistent."
            )
        if status not in VALID_ANALYTICAL_STATUSES:
            raise ValueError("Crosswalk resolution produced an unsupported analytical status.")
        crosswalk_type = (
            _crosswalk_relationship_type(row, previous_counts, current_counts)
            if partial and not source_problem
            else None
        )
        resolution_reason = (
            _partial_reason(row, crosswalk_type, policy.structural_overlap_percentage)
            if partial and not source_problem and crosswalk_type is not None
            else policy_reason
        )
        resolved.append(
            GeographicCrosswalkResolutionRow(
                mapping_id=row.mapping_id,
                previous_election_id=row.previous_election_id,
                previous_area_id=row.previous_area_id,
                previous_area_name=row.previous_area_name,
                current_election_id=row.current_election_id,
                current_area_id=row.current_area_id,
                current_area_name=row.current_area_name,
                relationship_type=row.relationship_type,
                crosswalk_relationship_type=crosswalk_type,
                crosswalk_component_id=component_ids.get(row.mapping_id),
                intersection_area_m2=row.overlap_area_m2,
                source_overlap_ratio=row.previous_area_overlap_percentage / 100,
                target_overlap_ratio=row.current_area_overlap_percentage / 100,
                GIS_source=row.GIS_source,
                boundary_source=row.boundary_source,
                analytical_status=status,
                resolution_reason_code=reason_code,
                decision_reason=resolution_reason,
                evidence_summary=row.evidence_summary,
                confidence=confidence,
                uncertainty=uncertainty,
                weight_availability=weight_availability,
                weight_type=weight_type,
                weight_recommendation=weight_recommendation,
                allowed_future_use=allowed_future_use,
                candidate_history_allowed=candidate_history_allowed,
                incumbency_allowed=incumbency_allowed,
                previous_winner_allowed=previous_winner_allowed,
            )
        )
    return tuple(resolved)


def direct_mappings_for_future_approved_use(
    rows: Sequence[GeographicCrosswalkResolutionRow],
) -> tuple[GeographicCrosswalkResolutionRow, ...]:
    """Expose only direct rows to a future separately authorised analysis stage."""

    return tuple(row for row in rows if row.analytical_status == "accepted_direct")


def geographic_crosswalk_resolution_dataset(
    rows: Sequence[GeographicCrosswalkResolutionRow],
    policy: GeographicCrosswalkResolutionPolicy,
) -> dict[str, object]:
    """Create direct, crosswalk, blocked and full audit datasets from one source list."""

    if not rows:
        raise ValueError("Geographic crosswalk resolution dataset requires rows.")
    audit_rows = [asdict(row) for row in rows]
    direct_rows = [row for row in audit_rows if row["analytical_status"] == "accepted_direct"]
    crosswalk_rows = [
        row
        for row in audit_rows
        if row["analytical_status"] == "partial_crosswalk_available"
    ]
    not_comparable_rows = [
        row for row in audit_rows if row["analytical_status"] == "not_comparable"
    ]
    requires_review_rows = [
        row for row in audit_rows if row["analytical_status"] == "requires_review"
    ]
    if len(audit_rows) != (
        len(direct_rows)
        + len(crosswalk_rows)
        + len(not_comparable_rows)
        + len(requires_review_rows)
    ):
        raise ValueError("Crosswalk resolution statuses must partition every decision row.")
    return {
        "framework_id": policy.framework_id,
        "summary": {
            "relationships_reviewed": len(audit_rows),
            "accepted_direct_mappings": len(direct_rows),
            "partial_crosswalk_relationships": len(crosswalk_rows),
            "not_comparable_relationships": len(not_comparable_rows),
            "requires_review_relationships": len(requires_review_rows),
            "crosswalk_components": len(
                {row["crosswalk_component_id"] for row in crosswalk_rows}
            ),
            "resolution_reason_counts": dict(
                sorted(Counter(row["resolution_reason_code"] for row in audit_rows).items())
            ),
            "historical_features_generated": False,
        },
        "methodology": {
            "direct_mapping": "Only the existing accepted_direct rows are strict one-to-one analytical matches.",
            "partial_crosswalk": (
                "A partial crosswalk preserves split, merged and many-to-many GIS topology. "
                "It never represents a direct electoral mapping."
            ),
            "not_comparable": (
                "A non-structural relationship below the documented overlap threshold is blocked "
                "from later historical analysis."
            ),
            "weighting_assessment": dict(policy.weighting_assessment),
            "weighting_reason": policy.weighting_reason,
            "prohibited_actions": list(policy.prohibited_actions),
        },
        "resolution_rows": audit_rows,
        "final_direct_mapping_dataset": direct_rows,
        "analytical_crosswalk_dataset": crosswalk_rows,
        "not_comparable_dataset": not_comparable_rows,
        "requires_review_dataset": requires_review_rows,
    }


def geographic_crosswalk_resolution_report_markdown(dataset: Mapping[str, Any]) -> str:
    """Render a concise report while keeping detailed evidence in the JSON datasets."""

    summary = dataset["summary"]
    methodology = dataset["methodology"]
    crosswalk_rows = dataset["analytical_crosswalk_dataset"]
    assert isinstance(summary, Mapping)
    assert isinstance(methodology, Mapping)
    assert isinstance(crosswalk_rows, list)
    topology = Counter(
        str(row["crosswalk_relationship_type"])
        for row in crosswalk_rows
    )
    reason_counts = summary["resolution_reason_counts"]
    assert isinstance(reason_counts, Mapping)
    lines = [
        "# Surrey Geographic Crosswalk Resolution Report",
        "",
        "## Resolution outcome",
        "",
        f"- Relationships reviewed: {summary['relationships_reviewed']}",
        f"- Accepted direct mappings: {summary['accepted_direct_mappings']}",
        f"- Partial crosswalk relationships: {summary['partial_crosswalk_relationships']}",
        f"- Not comparable relationships: {summary['not_comparable_relationships']}",
        f"- Requires-review relationships: {summary['requires_review_relationships']}",
        f"- Crosswalk topology components: {summary['crosswalk_components']}",
        f"- Historical features generated: {summary['historical_features_generated']}",
        "",
        "## Direct mapping and partial crosswalk are different",
        "",
        str(methodology["direct_mapping"]),
        "",
        str(methodology["partial_crosswalk"]),
        "",
        "## Partial crosswalk topology",
        "",
    ]
    for relationship_type, count in sorted(topology.items()):
        lines.append(f"- {relationship_type}: {count}")
    lines.extend(
        [
            "",
            "## Structured unresolved reasons",
            "",
        ]
    )
    for reason_code, count in sorted(reason_counts.items()):
        if reason_code != "accepted_direct_criteria_pass":
            lines.append(f"- {reason_code}: {count}")
    lines.extend(
        [
            "",
            "## Weighting position",
            "",
            str(methodology["weighting_reason"]),
            "",
            "No numeric electorate, population, residential or area weight has been created.",
            "",
            "## Downstream protection",
            "",
        ]
    )
    for action in methodology["prohibited_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def geographic_crosswalk_methodology_markdown(
    policy: GeographicCrosswalkResolutionPolicy,
) -> str:
    """Document the distinction between topology evidence and electoral comparison."""

    return "\n".join(
        [
            "# Surrey Geographic Crosswalk Resolution Methodology",
            "",
            "## Classification rules",
            "",
            f"A material structural relationship uses at least {policy.structural_overlap_percentage:.1f}% "
            "mutual GIS overlap. Any relationship attached to a material multi-area component is "
            "retained as a partial crosswalk edge, including small edges needed to preserve topology.",
            "",
            "- accepted_direct: strict existing one-to-one GIS decision; eligible only after future explicit approval.",
            "- partial_crosswalk_available: one-to-many, many-to-one or many-to-many boundary topology; electoral use is blocked.",
            "- not_comparable: non-structural low-overlap relationship; all historical analysis is blocked.",
            "- requires_review: potentially one-to-one relationship that still fails strict direct criteria.",
            "- geometry_validation_failure or boundary_source_inconsistency: source remediation is required before any topology decision.",
            "",
            "## Weighting limitations",
            "",
            policy.weighting_reason,
            "",
            "Area ratios are retained as GIS evidence, not as vote weights. Candidate history, incumbency "
            "and previous-winner transfer require stricter rules than geographic overlap and remain blocked.",
            "",
        ]
    )
