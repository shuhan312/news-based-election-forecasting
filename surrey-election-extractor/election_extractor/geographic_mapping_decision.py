"""Apply documented mapping decisions without creating automatic equivalence.

This module is deliberately downstream of the GIS review dataset.  It records
why each candidate remains unresolved and exposes only explicitly approved,
evidence-complete rows to any future enrichment work.  It does not calculate
vote change, incumbency, candidate history or any other electoral feature.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from election_extractor.geographic_mapping_review import GeographicMappingReviewRow


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECISION_POLICY_PATH = PROJECT_ROOT / "config/geographic_mapping_decision_policy.json"
VALID_MAPPING_TYPES = frozenset({"exact", "near_exact", "split", "merged", "uncertain"})
VALID_DECISIONS = frozenset({"accepted", "rejected", "requires_review"})
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})


@dataclass(frozen=True)
class MappingDecisionPolicy:
    """Keep decision criteria in a readable configuration rather than hidden rules."""

    framework_id: str
    acceptance_rules: Mapping[str, Mapping[str, object]]
    direct_historical_to_2026_boundary_crosswalk_available: bool
    current_evidence_reason: str
    prohibited_actions: tuple[str, ...]


@dataclass(frozen=True)
class GeographicMappingDecisionRow:
    """One transparent decision for a GIS candidate, not an electoral calculation."""

    mapping_id: str
    previous_election_id: str
    previous_area_id: str
    previous_area_name: str
    current_election_id: str
    current_area_id: str
    current_area_name: str
    mapping_type: str
    confidence: str
    decision: str
    gis_source: str
    boundary_source: str
    evidence_notes: str
    reviewer_reason: str
    evidence_summary: str


@dataclass(frozen=True)
class ManualMappingDecision:
    """An explicit future reviewer instruction; no instruction is implied by GIS."""

    mapping_id: str
    decision: str
    confidence: str
    reviewer_reason: str
    direct_boundary_evidence: str | None = None
    evidence_summary: str | None = None


def _required_text(value: object, field_name: str) -> str:
    """Reject undocumented decisions instead of completing them with defaults."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Geographic mapping decision requires non-empty {field_name}.")
    return value.strip()


def load_mapping_decision_policy(
    path: str | Path = DEFAULT_DECISION_POLICY_PATH,
) -> MappingDecisionPolicy:
    """Load transparent rules without reading election data or changing mappings."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Geographic mapping decision policy must be an object.")
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
    if not isinstance(direct_crosswalk, bool):
        raise ValueError("Decision policy requires a boolean direct-crosswalk flag.")
    prohibited = payload.get("prohibited_actions")
    if not isinstance(prohibited, list) or not prohibited:
        raise ValueError("Decision policy requires prohibited_actions.")
    return MappingDecisionPolicy(
        framework_id=_required_text(payload.get("framework_id"), "framework_id"),
        acceptance_rules=rules,
        direct_historical_to_2026_boundary_crosswalk_available=direct_crosswalk,
        current_evidence_reason=_required_text(evidence_assessment.get("reason"), "reason"),
        prohibited_actions=tuple(_required_text(item, "prohibited action") for item in prohibited),
    )


def _manual_decisions_by_id(
    decisions: Sequence[ManualMappingDecision],
) -> dict[str, ManualMappingDecision]:
    """Require reviewer instructions to be unambiguous and individually identified."""

    indexed: dict[str, ManualMappingDecision] = {}
    for item in decisions:
        if item.decision not in VALID_DECISIONS:
            raise ValueError("Manual mapping decision has an unsupported decision value.")
        if item.confidence not in VALID_CONFIDENCE:
            raise ValueError("Manual mapping decision has an unsupported confidence value.")
        if not item.reviewer_reason.strip():
            raise ValueError("Manual mapping decision requires reviewer_reason.")
        if item.mapping_id in indexed:
            raise ValueError("Manual mapping decisions cannot repeat mapping_id.")
        indexed[item.mapping_id] = item
    return indexed


def _default_reason(row: GeographicMappingReviewRow, policy: MappingDecisionPolicy) -> str:
    """State the unresolved reason without overstating GIS or legal evidence."""

    if row.mapping_type == "exact":
        return (
            "GIS shows near-total one-to-one coverage, but the current legal evidence "
            "does not directly establish this historical division as the same area as the 2026 ward."
        )
    if row.mapping_type == "near_exact":
        return (
            "GIS indicates a likely comparable one-to-one area, but direct legal equivalence "
            "and a manual explanation of the remaining boundary difference are absent."
        )
    if row.mapping_type == "split":
        return (
            "The historical division has material overlap with multiple 2026 wards; "
            "a one-to-one mapping would be unsupported."
        )
    if row.mapping_type == "merged":
        return (
            "The 2026 ward has material overlap with multiple historical divisions; "
            "a one-to-one mapping would be unsupported."
        )
    return (
        "The available GIS evidence does not establish a comparable one-to-one geography; "
        "the relationship remains unresolved."
    )


def _mapping_confidence(row: GeographicMappingReviewRow, policy: MappingDecisionPolicy) -> str:
    """Report confidence in final equivalence, not confidence in the GIS calculation."""

    # GIS may be exact, but no direct historic-to-2026 legal crosswalk is
    # currently available. The mapping claim therefore cannot receive a high
    # or medium final-equivalence confidence merely from overlap percentages.
    if not policy.direct_historical_to_2026_boundary_crosswalk_available:
        return "low"
    return row.confidence


def _validate_accepted_decision(
    row: GeographicMappingReviewRow,
    decision: ManualMappingDecision,
) -> None:
    """Make acceptance impossible without pair-specific evidence and reasoning."""

    if row.mapping_type not in {"exact", "near_exact"}:
        raise ValueError("Only exact or near_exact candidates can be manually accepted.")
    if not decision.direct_boundary_evidence or not decision.direct_boundary_evidence.strip():
        raise ValueError("Accepted mapping requires direct_boundary_evidence.")
    if not decision.evidence_summary or not decision.evidence_summary.strip():
        raise ValueError("Accepted mapping requires evidence_summary.")


def build_geographic_mapping_decisions(
    review_rows: Sequence[GeographicMappingReviewRow],
    policy: MappingDecisionPolicy,
    manual_decisions: Sequence[ManualMappingDecision] = (),
) -> tuple[GeographicMappingDecisionRow, ...]:
    """Create decision rows while refusing any automatic GIS-to-mapping conversion."""

    if not review_rows:
        raise ValueError("Geographic mapping decision framework requires review rows.")
    manual_by_id = _manual_decisions_by_id(manual_decisions)
    review_ids = {row.mapping_id for row in review_rows}
    unknown_ids = sorted(set(manual_by_id) - review_ids)
    if unknown_ids:
        raise ValueError("Manual mapping decision references an unknown mapping_id.")

    results = []
    for row in review_rows:
        if row.mapping_type not in VALID_MAPPING_TYPES:
            raise ValueError("Review row has an unsupported mapping_type.")
        manual = manual_by_id.get(row.mapping_id)
        if manual is None:
            decision = "requires_review"
            confidence = _mapping_confidence(row, policy)
            reviewer_reason = _default_reason(row, policy)
            boundary_source = row.legal_boundary_source
            evidence_summary = (
                "Official GIS sources and the retained 2026 legal source are present, "
                "but no direct historical-division-to-2026-ward legal crosswalk is available."
            )
        else:
            if manual.decision == "accepted":
                _validate_accepted_decision(row, manual)
            decision = manual.decision
            confidence = manual.confidence
            reviewer_reason = manual.reviewer_reason.strip()
            boundary_source = manual.direct_boundary_evidence or row.legal_boundary_source
            evidence_summary = (manual.evidence_summary or policy.current_evidence_reason).strip()
        results.append(
            GeographicMappingDecisionRow(
                mapping_id=row.mapping_id,
                previous_election_id=row.previous_election,
                previous_area_id=row.previous_area_id,
                previous_area_name=row.previous_area_name,
                current_election_id=row.current_election,
                current_area_id=row.current_area_id,
                current_area_name=row.current_area_name,
                mapping_type=row.mapping_type,
                confidence=confidence,
                decision=decision,
                gis_source=row.gis_source,
                boundary_source=boundary_source,
                evidence_notes=row.notes,
                reviewer_reason=reviewer_reason,
                evidence_summary=evidence_summary,
            )
        )
    return tuple(results)


def approved_mappings_for_future_enrichment(
    decisions: Sequence[GeographicMappingDecisionRow],
) -> tuple[dict[str, str], ...]:
    """Expose only evidence-complete accepted rows to a future enrichment stage.

    This guard is intentionally not an enrichment implementation. It returns
    zero rows for unresolved, split, merged and rejected candidates, preventing
    a later vote-change or incumbency calculation from accidentally using them.
    """

    approved = []
    for row in decisions:
        if row.decision != "accepted":
            continue
        if row.mapping_type not in {"exact", "near_exact"}:
            raise ValueError("Split, merged or uncertain mappings cannot be approved for enrichment.")
        if not row.gis_source or not row.boundary_source or not row.reviewer_reason:
            raise ValueError("Accepted mapping is missing required evidence.")
        approved.append(
            {
                "mapping_id": row.mapping_id,
                "previous_election_id": row.previous_election_id,
                "previous_area_id": row.previous_area_id,
                "previous_area_name": row.previous_area_name,
                "current_election_id": row.current_election_id,
                "current_area_id": row.current_area_id,
                "current_area_name": row.current_area_name,
                "mapping_type": row.mapping_type,
                "confidence": row.confidence,
                "decision": row.decision,
                "GIS_source": row.gis_source,
                "boundary_source": row.boundary_source,
                "evidence_notes": row.evidence_notes,
            }
        )
    return tuple(approved)


def geographic_mapping_decision_summary(
    decisions: Sequence[GeographicMappingDecisionRow],
) -> dict[str, object]:
    """Summarise decisions without turning summary counts into mappings."""

    if not decisions:
        raise ValueError("Geographic mapping decision summary requires decision rows.")
    decision_counts = Counter(row.decision for row in decisions)
    type_counts = Counter(row.mapping_type for row in decisions)
    return {
        "candidate_relationships_reviewed": len(decisions),
        "accepted_mappings": decision_counts["accepted"],
        "rejected_mappings": decision_counts["rejected"],
        "requires_review_mappings": decision_counts["requires_review"],
        "split_cases": type_counts["split"],
        "merged_cases": type_counts["merged"],
        "final_geographic_mapping_rows": len(approved_mappings_for_future_enrichment(decisions)),
        "historical_features_generated": False,
    }


def geographic_mapping_decision_dataset(
    decisions: Sequence[GeographicMappingDecisionRow],
    policy: MappingDecisionPolicy,
) -> dict[str, object]:
    """Prepare a complete JSON-ready audit dataset and methodology record."""

    return {
        "framework_id": policy.framework_id,
        "summary": geographic_mapping_decision_summary(decisions),
        "methodology": {
            "acceptance_rules": dict(policy.acceptance_rules),
            "current_evidence_assessment": {
                "direct_historical_to_2026_boundary_crosswalk_available": (
                    policy.direct_historical_to_2026_boundary_crosswalk_available
                ),
                "reason": policy.current_evidence_reason,
            },
            "prohibited_actions": list(policy.prohibited_actions),
        },
        "decision_rows": [asdict(row) for row in decisions],
    }


def geographic_mapping_decision_report_markdown(dataset: Mapping[str, Any]) -> str:
    """Render an auditable decision report with every candidate's reasoning."""

    summary = dataset["summary"]
    methodology = dataset["methodology"]
    rows = dataset["decision_rows"]
    assert isinstance(summary, Mapping)
    assert isinstance(methodology, Mapping)
    assert isinstance(rows, list)
    lines = [
        "# Surrey Geographic Mapping Decision Report",
        "",
        "## Decision outcome",
        "",
        f"- Candidate relationships reviewed: {summary['candidate_relationships_reviewed']}",
        f"- Accepted: {summary['accepted_mappings']}",
        f"- Rejected: {summary['rejected_mappings']}",
        f"- Requires review: {summary['requires_review_mappings']}",
        f"- Split cases: {summary['split_cases']}",
        f"- Merged cases: {summary['merged_cases']}",
        f"- Final Geographic Mapping rows: {summary['final_geographic_mapping_rows']}",
        f"- Historical features generated: {summary['historical_features_generated']}",
        "",
        "## Methodology",
        "",
        "A GIS overlap is a candidate only. Exact and near_exact classifications "
        "need direct official boundary evidence before acceptance. Split and merged "
        "relationships cannot be treated as one-to-one mappings. Uncertain relationships "
        "remain unresolved.",
        "",
        "## Current limitation",
        "",
        str(methodology["current_evidence_assessment"]["reason"]),
        "",
        "## Candidate decisions",
        "",
        "| Mapping ID | Previous area | Current area | Type | Decision | Confidence | Reviewer reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        assert isinstance(row, Mapping)
        lines.append(
            "| {mapping_id} | {previous_area_name} | {current_area_name} | {mapping_type} | "
            "{decision} | {confidence} | {reviewer_reason} |".format(**row)
        )
    lines.extend(["", "## Prohibited actions", ""])
    for action in methodology["prohibited_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def geographic_mapping_methodology_markdown(policy: MappingDecisionPolicy) -> str:
    """Render the standalone methodology requested for review and future reuse."""

    lines = [
        "# Surrey Geographic Mapping Decision Methodology",
        "",
        "## Acceptance rules",
        "",
    ]
    for mapping_type in sorted(policy.acceptance_rules):
        rule = policy.acceptance_rules[mapping_type]
        lines.extend(
            [
                f"### {mapping_type}",
                "",
                str(rule["acceptance_threshold"]),
                "",
            ]
        )
    lines.extend(
        [
            "## Limitations",
            "",
            "GIS area overlap alone does not prove that two electoral geographies are "
            "equivalent, contain the same electorate, or support a direct historical "
            "comparison. Shared names and largest-overlap relationships are not evidence "
            "of equivalence. Only a future documented decision with direct boundary evidence "
            "may provide a mapping to a separately authorised enrichment stage.",
            "",
        ]
    )
    return "\n".join(lines)
