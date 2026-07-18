"""Decide analytical geographic comparability without asserting legal identity.

GIS evidence can support a strict, one-to-one analytical bridge between a
historic Surrey division and a 2026 ward. It cannot by itself prove that the
two areas are legally identical. This module preserves that distinction and
never calculates political or electoral comparison fields.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from election_extractor.geographic_mapping_review import GeographicMappingReviewRow


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECISION_POLICY_PATH = PROJECT_ROOT / "config/geographic_mapping_decision_policy.json"
VALID_MAPPING_TYPES = frozenset({"exact", "near_exact", "split", "merged", "uncertain"})
VALID_ADMINISTRATIVE_IDENTITY = frozenset({"confirmed", "not_confirmed", "uncertain"})
VALID_ANALYTICAL_COMPARABILITY = frozenset(
    {"accepted_direct", "requires_review", "not_comparable"}
)


@dataclass(frozen=True)
class MappingDecisionPolicy:
    """Store auditable direct-match thresholds outside the decision code."""

    framework_id: str
    minimum_mutual_overlap_percentage: float
    maximum_competing_overlap_percentage: float
    require_valid_geometry: bool
    require_consistent_boundary_sources: bool
    direct_rules_explanation: str
    acceptance_rules: Mapping[str, Mapping[str, object]]
    direct_historical_to_2026_boundary_crosswalk_available: bool
    current_evidence_reason: str
    prohibited_actions: tuple[str, ...]


@dataclass(frozen=True)
class GeographicMappingDecisionRow:
    """One source-preserving decision for a single GIS candidate relationship."""

    mapping_id: str
    previous_election_id: str
    previous_area_id: str
    previous_area_name: str
    current_election_id: str
    current_area_id: str
    current_area_name: str
    overlap_area_m2: float
    previous_area_overlap_percentage: float
    current_area_overlap_percentage: float
    largest_previous_area_competitor_percentage: float
    largest_current_area_competitor_percentage: float
    geometry_valid: bool
    boundary_sources_consistent: bool
    relationship_type: str
    administrative_identity: str
    analytical_comparability: str
    confidence: str
    decision: str
    GIS_source: str
    boundary_source: str
    evidence_notes: str
    reviewer_reason: str
    evidence_summary: str


def _required_text(value: object, field_name: str) -> str:
    """Reject absent policy or evidence text instead of inventing a value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Geographic mapping decision requires non-empty {field_name}.")
    return value.strip()


def _required_number(value: object, field_name: str) -> float:
    """Require recorded numeric evidence for a direct analytical decision."""

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Geographic mapping decision requires numeric {field_name}.")
    return float(value)


def _required_bool(value: object, field_name: str) -> bool:
    """Require an explicit geometry or source-consistency result."""

    if not isinstance(value, bool):
        raise ValueError(f"Geographic mapping decision requires boolean {field_name}.")
    return value


def load_mapping_decision_policy(
    path: str | Path = DEFAULT_DECISION_POLICY_PATH,
) -> MappingDecisionPolicy:
    """Load documented thresholds and restrictions without reading election results."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Geographic mapping decision policy must be an object.")
    direct_rules = payload.get("analytical_direct_rules")
    if not isinstance(direct_rules, Mapping):
        raise ValueError("Decision policy requires analytical_direct_rules.")
    minimum_overlap = _required_number(
        direct_rules.get("minimum_mutual_overlap_percentage"),
        "minimum_mutual_overlap_percentage",
    )
    maximum_competitor = _required_number(
        direct_rules.get("maximum_competing_overlap_percentage"),
        "maximum_competing_overlap_percentage",
    )
    if not 0 < minimum_overlap <= 100:
        raise ValueError("minimum_mutual_overlap_percentage must be between zero and 100.")
    if not 0 <= maximum_competitor < minimum_overlap:
        raise ValueError("maximum_competing_overlap_percentage is not valid.")
    raw_rules = payload.get("acceptance_rules")
    if not isinstance(raw_rules, Mapping) or set(raw_rules) != VALID_MAPPING_TYPES:
        raise ValueError("Decision policy must define each supported mapping type exactly once.")
    rules: dict[str, Mapping[str, object]] = {}
    for mapping_type, rule in raw_rules.items():
        if not isinstance(rule, Mapping):
            raise ValueError(f"Decision policy rule for {mapping_type} must be an object.")
        _required_text(rule.get("decision_without_direct_boundary_evidence"), "default decision")
        _required_text(rule.get("acceptance_threshold"), "acceptance_threshold")
        rules[str(mapping_type)] = rule
    evidence_assessment = payload.get("current_evidence_assessment")
    if not isinstance(evidence_assessment, Mapping):
        raise ValueError("Decision policy requires current_evidence_assessment.")
    direct_crosswalk = evidence_assessment.get(
        "direct_historical_to_2026_boundary_crosswalk_available"
    )
    prohibited = payload.get("prohibited_actions")
    if not isinstance(direct_crosswalk, bool):
        raise ValueError("Decision policy requires a boolean direct-crosswalk flag.")
    if not isinstance(prohibited, list) or not prohibited:
        raise ValueError("Decision policy requires prohibited_actions.")
    return MappingDecisionPolicy(
        framework_id=_required_text(payload.get("framework_id"), "framework_id"),
        minimum_mutual_overlap_percentage=minimum_overlap,
        maximum_competing_overlap_percentage=maximum_competitor,
        require_valid_geometry=_required_bool(
            direct_rules.get("require_valid_geometry"),
            "require_valid_geometry",
        ),
        require_consistent_boundary_sources=_required_bool(
            direct_rules.get("require_consistent_boundary_sources"),
            "require_consistent_boundary_sources",
        ),
        direct_rules_explanation=_required_text(direct_rules.get("explanation"), "explanation"),
        acceptance_rules=rules,
        direct_historical_to_2026_boundary_crosswalk_available=direct_crosswalk,
        current_evidence_reason=_required_text(evidence_assessment.get("reason"), "reason"),
        prohibited_actions=tuple(_required_text(item, "prohibited action") for item in prohibited),
    )


def _overlap_percentage(row: GeographicMappingReviewRow) -> float:
    """Use the smaller directional coverage as the conservative direct-match score."""

    return min(
        row.previous_area_overlap_percentage,
        row.current_area_overlap_percentage,
    )


def _largest_competitors(
    rows: Sequence[GeographicMappingReviewRow],
) -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    """Measure competitors without selecting a largest-overlap mapping as truth."""

    old_groups: defaultdict[str, list[GeographicMappingReviewRow]] = defaultdict(list)
    current_groups: defaultdict[tuple[str, str], list[GeographicMappingReviewRow]] = defaultdict(list)
    for row in rows:
        old_groups[row.previous_area_id].append(row)
        current_groups[(row.current_election, row.current_area_id)].append(row)
    old_competitors: dict[str, float] = {}
    current_competitors: dict[tuple[str, str], float] = {}
    for key, group in old_groups.items():
        ordered = sorted((_overlap_percentage(row) for row in group), reverse=True)
        old_competitors[key] = ordered[1] if len(ordered) > 1 else 0.0
    for key, group in current_groups.items():
        ordered = sorted((_overlap_percentage(row) for row in group), reverse=True)
        current_competitors[key] = ordered[1] if len(ordered) > 1 else 0.0
    return old_competitors, current_competitors


def _administrative_identity(policy: MappingDecisionPolicy) -> str:
    """Keep legal confirmation separate from a GIS-supported analytical decision."""

    return "confirmed" if policy.direct_historical_to_2026_boundary_crosswalk_available else "not_confirmed"


def _direct_failures(
    row: GeographicMappingReviewRow,
    policy: MappingDecisionPolicy,
    previous_competitor: float,
    current_competitor: float,
) -> tuple[str, ...]:
    """List the precise failed direct criteria for an auditable unresolved decision."""

    failures = []
    # This tolerance is an evidence-policy boundary, not a rounding shortcut.
    # The configured value is calibrated to LGBCE's published count of 24
    # unchanged Surrey divisions; the competitor gates still prevent split or
    # merged geographies from passing only because their largest overlap is high.
    if row.mapping_type not in {"exact", "near_exact"}:
        failures.append(f"relationship type is {row.mapping_type}, not a one-to-one candidate")
    if _overlap_percentage(row) < policy.minimum_mutual_overlap_percentage:
        failures.append(
            "mutual overlap "
            f"{_overlap_percentage(row):.6f}% is below "
            f"{policy.minimum_mutual_overlap_percentage:.6f}%"
        )
    if previous_competitor >= policy.maximum_competing_overlap_percentage:
        failures.append(
            "historical-area competing overlap "
            f"{previous_competitor:.6f}% is significant"
        )
    if current_competitor >= policy.maximum_competing_overlap_percentage:
        failures.append(
            "current-ward competing overlap "
            f"{current_competitor:.6f}% is significant"
        )
    if policy.require_valid_geometry and not row.geometry_valid:
        failures.append("one or both source geometries are invalid")
    if policy.require_consistent_boundary_sources and not row.boundary_sources_consistent:
        failures.append("configured boundary sources are not consistent")
    return tuple(failures)


def _unresolved_reason(row: GeographicMappingReviewRow, failures: Sequence[str]) -> str:
    """Explain why an unresolved candidate cannot become a direct bridge."""

    if row.mapping_type == "split":
        return "Split relationship: old area maps materially to multiple new wards; one-to-one comparison is not permitted."
    if row.mapping_type == "merged":
        return "Merged relationship: new ward maps materially to multiple old areas; one-to-one comparison is not permitted."
    if failures:
        return "Direct analytical criteria not met: " + "; ".join(failures) + "."
    return "Relationship remains unresolved pending additional review."


def _unresolved_confidence(row: GeographicMappingReviewRow) -> str:
    """Use the existing GIS evidence score without representing it as approval."""

    return "medium" if row.mapping_type in {"exact", "near_exact"} else "low"


def build_geographic_mapping_decisions(
    review_rows: Sequence[GeographicMappingReviewRow],
    policy: MappingDecisionPolicy,
) -> tuple[GeographicMappingDecisionRow, ...]:
    """Classify all candidates and accept only strict analytical direct matches.

    The function does not use names to decide a mapping.  It also does not need
    legal identity confirmation for an ``accepted_direct`` analytical match;
    that distinct legal status remains ``not_confirmed`` unless a direct
    historical-to-2026 legal crosswalk becomes available.
    """

    if not review_rows:
        raise ValueError("Geographic mapping decision framework requires review rows.")
    if len({row.mapping_id for row in review_rows}) != len(review_rows):
        raise ValueError("Geographic mapping decision rows require unique mapping_id values.")
    old_competitors, current_competitors = _largest_competitors(review_rows)
    rows = []
    for row in review_rows:
        if row.mapping_type not in VALID_MAPPING_TYPES:
            raise ValueError("Review row has an unsupported mapping_type.")
        previous_competitor = old_competitors[row.previous_area_id]
        current_competitor = current_competitors[(row.current_election, row.current_area_id)]
        failures = _direct_failures(
            row,
            policy,
            previous_competitor,
            current_competitor,
        )
        direct_match = not failures
        administrative_identity = _administrative_identity(policy)
        if direct_match:
            analytical_comparability = "accepted_direct"
            decision = "accepted"
            confidence = "high"
            reviewer_reason = (
                "Passes the configured strict one-to-one GIS criteria: high mutual coverage, "
                "no significant competing overlap, valid geometry and consistent sources. "
                "This is an analytical match and does not claim legal identity."
            )
        else:
            analytical_comparability = (
                "not_comparable" if row.mapping_type in {"split", "merged"} else "requires_review"
            )
            decision = "requires_review"
            confidence = _unresolved_confidence(row)
            reviewer_reason = _unresolved_reason(row, failures)
        evidence_summary = (
            f"Mutual overlap={_overlap_percentage(row):.6f}%; "
            f"largest historic competitor={previous_competitor:.6f}%; "
            f"largest current competitor={current_competitor:.6f}%; "
            f"geometry_valid={row.geometry_valid}; "
            f"boundary_sources_consistent={row.boundary_sources_consistent}."
        )
        rows.append(
            GeographicMappingDecisionRow(
                mapping_id=row.mapping_id,
                previous_election_id=row.previous_election,
                previous_area_id=row.previous_area_id,
                previous_area_name=row.previous_area_name,
                current_election_id=row.current_election,
                current_area_id=row.current_area_id,
                current_area_name=row.current_area_name,
                overlap_area_m2=row.overlap_area_m2,
                previous_area_overlap_percentage=row.previous_area_overlap_percentage,
                current_area_overlap_percentage=row.current_area_overlap_percentage,
                largest_previous_area_competitor_percentage=previous_competitor,
                largest_current_area_competitor_percentage=current_competitor,
                geometry_valid=row.geometry_valid,
                boundary_sources_consistent=row.boundary_sources_consistent,
                relationship_type=row.mapping_type,
                administrative_identity=administrative_identity,
                analytical_comparability=analytical_comparability,
                confidence=confidence,
                decision=decision,
                GIS_source=row.gis_source,
                boundary_source=row.legal_boundary_source,
                evidence_notes=row.notes,
                reviewer_reason=reviewer_reason,
                evidence_summary=evidence_summary,
            )
        )
    return tuple(rows)


def approved_mappings_for_future_enrichment(
    decisions: Sequence[GeographicMappingDecisionRow],
) -> tuple[dict[str, object], ...]:
    """Expose only ``accepted_direct`` rows to a future, separately authorised stage."""

    approved = []
    for row in decisions:
        if row.analytical_comparability != "accepted_direct":
            continue
        if row.decision != "accepted" or row.relationship_type not in {"exact", "near_exact"}:
            raise ValueError("Only accepted exact or near_exact rows may enter enrichment.")
        if not row.geometry_valid or not row.boundary_sources_consistent:
            raise ValueError("Accepted direct mapping requires valid, consistent boundary evidence.")
        approved.append(
            {
                "mapping_id": row.mapping_id,
                "previous_election_id": row.previous_election_id,
                "previous_area_id": row.previous_area_id,
                "previous_area_name": row.previous_area_name,
                "current_election_id": row.current_election_id,
                "current_area_id": row.current_area_id,
                "current_area_name": row.current_area_name,
                "mapping_type": row.relationship_type,
                "administrative_identity": row.administrative_identity,
                "analytical_comparability": row.analytical_comparability,
                "confidence": row.confidence,
                "decision": row.decision,
                "GIS_source": row.GIS_source,
                "boundary_source": row.boundary_source,
                "evidence_notes": row.evidence_notes,
            }
        )
    return tuple(approved)


def geographic_mapping_decision_summary(
    decisions: Sequence[GeographicMappingDecisionRow],
) -> dict[str, object]:
    """Report decisions without calculating a single political comparison field."""

    if not decisions:
        raise ValueError("Geographic mapping decision summary requires decision rows.")
    decision_counts = Counter(row.decision for row in decisions)
    relationship_counts = Counter(row.relationship_type for row in decisions)
    comparability_counts = Counter(row.analytical_comparability for row in decisions)
    return {
        "candidate_relationships_reviewed": len(decisions),
        "accepted_direct_mappings": comparability_counts["accepted_direct"],
        "rejected_mappings": decision_counts["rejected"],
        "requires_review_mappings": decision_counts["requires_review"],
        "not_comparable_mappings": comparability_counts["not_comparable"],
        "split_cases": relationship_counts["split"],
        "merged_cases": relationship_counts["merged"],
        # These are approved decision-output rows only. They are not a claim
        # that historical election tables have been joined or compared.
        "approved_direct_mapping_rows": len(approved_mappings_for_future_enrichment(decisions)),
        "historical_features_generated": False,
    }


def geographic_mapping_decision_dataset(
    decisions: Sequence[GeographicMappingDecisionRow],
    policy: MappingDecisionPolicy,
) -> dict[str, object]:
    """Create the full traceable decision dataset and its documented criteria."""

    # Keep the complete 167-row audit as the primary record. The two derived
    # lists below are transparent views, not a second source of mapping data.
    decision_rows = [asdict(row) for row in decisions]
    approved_rows = [
        row for row in decision_rows if row["analytical_comparability"] == "accepted_direct"
    ]
    unresolved_rows = [
        row for row in decision_rows if row["analytical_comparability"] != "accepted_direct"
    ]
    return {
        "framework_id": policy.framework_id,
        "summary": geographic_mapping_decision_summary(decisions),
        "methodology": {
            "legal_identity_distinction": (
                "Administrative identity is a legal claim; analytical comparability is a "
                "strict GIS-supported one-to-one decision. GIS never confirms legal identity."
            ),
            "analytical_direct_rules": {
                "minimum_mutual_overlap_percentage": policy.minimum_mutual_overlap_percentage,
                "maximum_competing_overlap_percentage": policy.maximum_competing_overlap_percentage,
                "require_valid_geometry": policy.require_valid_geometry,
                "require_consistent_boundary_sources": policy.require_consistent_boundary_sources,
                "explanation": policy.direct_rules_explanation,
            },
            "acceptance_rules": dict(policy.acceptance_rules),
            "current_legal_evidence": {
                "direct_historical_to_2026_boundary_crosswalk_available": (
                    policy.direct_historical_to_2026_boundary_crosswalk_available
                ),
                "reason": policy.current_evidence_reason,
            },
            "prohibited_actions": list(policy.prohibited_actions),
        },
        "decision_rows": decision_rows,
        "approved_direct_mappings": approved_rows,
        "unresolved_mappings": unresolved_rows,
    }


def geographic_mapping_decision_report_markdown(dataset: Mapping[str, Any]) -> str:
    """Render the complete decision audit with every relationship still traceable."""

    summary = dataset["summary"]
    methodology = dataset["methodology"]
    rows = dataset["decision_rows"]
    approved_rows = dataset["approved_direct_mappings"]
    unresolved_rows = dataset["unresolved_mappings"]
    assert isinstance(summary, Mapping)
    assert isinstance(methodology, Mapping)
    assert isinstance(rows, list)
    assert isinstance(approved_rows, list)
    assert isinstance(unresolved_rows, list)
    rules = methodology["analytical_direct_rules"]
    assert isinstance(rules, Mapping)
    lines = [
        "# Surrey Geographic Mapping Decision Report",
        "",
        "## Decision outcome",
        "",
        f"- Candidate relationships reviewed: {summary['candidate_relationships_reviewed']}",
        f"- Accepted direct analytical mappings: {summary['accepted_direct_mappings']}",
        f"- Requires review: {summary['requires_review_mappings']}",
        f"- Not comparable as one-to-one: {summary['not_comparable_mappings']}",
        f"- Split cases: {summary['split_cases']}",
        f"- Merged cases: {summary['merged_cases']}",
        f"- Approved direct mapping rows: {summary['approved_direct_mapping_rows']}",
        f"- Historical features generated: {summary['historical_features_generated']}",
        "",
        "## Legal identity and analytical comparability",
        "",
        str(methodology["legal_identity_distinction"]),
        "",
        "## Direct analytical criteria",
        "",
        str(rules["explanation"]),
        "",
        "## Approved direct mappings",
        "",
        "Only these rows pass the configured analytical approval check. Their administrative "
        "identity remains separate and may still be not_confirmed.",
        "",
        "| Mapping ID | Previous area | Current area | Type | Confidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in approved_rows:
        assert isinstance(row, Mapping)
        lines.append(
            "| {mapping_id} | {previous_area_name} | {current_area_name} | "
            "{relationship_type} | {confidence} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Unresolved mappings",
            "",
            f"- Total unresolved: {len(unresolved_rows)}",
            "- Split and merged relationships remain not comparable one-to-one; all other "
            "unresolved rows failed one or more direct analytical criteria.",
            "",
        "## Candidate decisions",
        "",
        "| Mapping ID | Previous area | Current area | Type | Administrative identity | Analytical comparability | Decision | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        assert isinstance(row, Mapping)
        lines.append(
            "| {mapping_id} | {previous_area_name} | {current_area_name} | {relationship_type} | "
            "{administrative_identity} | {analytical_comparability} | {decision} | {reviewer_reason} |".format(**row)
        )
    lines.extend(["", "## Prohibited actions", ""])
    for action in methodology["prohibited_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def geographic_mapping_methodology_markdown(policy: MappingDecisionPolicy) -> str:
    """Render a standalone explanation of the approval and limitation rules."""

    lines = [
        "# Surrey Geographic Mapping Decision Methodology",
        "",
        "## Legal identity is not analytical comparability",
        "",
        "A GIS direct match may be analytically comparable even where administrative identity "
        "is not_confirmed. This does not state that the areas are legally identical. A direct "
        "legal crosswalk would be required to set administrative identity to confirmed.",
        "",
        "## Direct analytical acceptance rules",
        "",
        policy.direct_rules_explanation,
        "",
        "Names are retained for audit but are never used as an acceptance criterion.",
        "",
        "## Relationship handling",
        "",
        "- exact and near_exact: may be accepted_direct only when every configured GIS rule passes.",
        "- split and merged: not comparable as one-to-one; separate aggregate methodology would be required.",
        "- uncertain and failed direct criteria: remain requires_review.",
        "",
        "## Limitations",
        "",
        "GIS overlap alone cannot establish legal identity, comparable electorates or a valid "
        "political comparison. This framework therefore exposes only accepted_direct rows to a "
        "future separately authorised enrichment stage and calculates no historical features.",
        "",
    ]
    return "\n".join(lines)
