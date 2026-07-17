"""Audit explicit permission to use historic areas as 2026 references.

The geographic crosswalk decides whether two boundaries have a documented
spatial relationship.  This module is deliberately a second, narrower layer:
it decides whether a specific accepted-direct relationship has sufficient
official boundary evidence for limited *analytical* historical reference.

It never changes a crosswalk classification, official election result, or
source field.  In particular, approval does not assert legal succession and
does not permit candidate-identity, incumbency, swing, or vote-redistribution
inference.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PERMISSION_CONFIGURATION_PATH = (
    PROJECT_ROOT / "config/historical_reference_permissions.json"
)
DIRECT_STATUS = "accepted_direct"
APPROVED_STATUS = "approved_for_historical_reference"
INSUFFICIENT_STATUS = "insufficient_official_evidence"


@dataclass(frozen=True)
class OfficialBoundarySource:
    """One citable public source used by the permission decision."""

    source_id: str
    source_type: str
    source_url: str
    evidence_text: str
    scope: str


@dataclass(frozen=True)
class HistoricalReferencePermissionPolicy:
    """Store explicit approval constraints instead of embedding them in code."""

    framework_id: str
    purpose: str
    required_crosswalk_status: str
    required_source_ids: tuple[str, ...]
    minimum_mutual_overlap_percentage: float
    maximum_competing_overlap_percentage: float
    permitted_features: tuple[str, ...]
    prohibited_features: tuple[str, ...]
    limitation: str


@dataclass(frozen=True)
class HistoricalReferencePermissionRecord:
    """One auditable decision for an existing accepted-direct crosswalk row."""

    mapping_id: str
    previous_election_id: str | None
    previous_area_id: str
    previous_area_name: str
    historical_event_area_name: str
    current_election_id: str
    current_area_id: str
    current_area_name: str
    crosswalk_status: str
    historical_reference_status: str
    previous_winner_allowed: bool
    candidate_history_allowed: bool
    incumbency_allowed: bool
    party_vote_share_change_allowed: bool
    source_ids: tuple[str, ...]
    source_urls: tuple[str, ...]
    evidence_summary: str
    uncertainty: str


def _required_text(value: object, field_name: str) -> str:
    """Reject missing configuration evidence rather than inventing a default."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Historical-reference permission requires non-empty {field_name}.")
    return value.strip()


def _required_number(value: object, field_name: str) -> float:
    """Require configured thresholds so every approval is reproducible."""

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Historical-reference permission requires numeric {field_name}.")
    return float(value)


def _https_url(value: object, field_name: str) -> str:
    """Accept only explicit public HTTPS source URLs for provenance evidence."""

    url = _required_text(value, field_name)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"Historical-reference permission requires HTTPS {field_name}.")
    return url


def _source_registry(raw_sources: object) -> dict[str, OfficialBoundarySource]:
    """Load the source registry and reject duplicate identifiers or opaque URLs."""

    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("Historical-reference permission requires source_registry.")
    sources: dict[str, OfficialBoundarySource] = {}
    for raw_source in raw_sources:
        if not isinstance(raw_source, Mapping):
            raise ValueError("Historical-reference permission source entries must be objects.")
        source = OfficialBoundarySource(
            source_id=_required_text(raw_source.get("source_id"), "source_id"),
            source_type=_required_text(raw_source.get("source_type"), "source_type"),
            source_url=_https_url(raw_source.get("source_url"), "source_url"),
            evidence_text=_required_text(raw_source.get("evidence_text"), "evidence_text"),
            scope=_required_text(raw_source.get("scope"), "scope"),
        )
        if source.source_id in sources:
            raise ValueError(f"Duplicate historical-reference source ID: {source.source_id}.")
        sources[source.source_id] = source
    return sources


def load_historical_reference_permission_configuration(
    path: str | Path = DEFAULT_PERMISSION_CONFIGURATION_PATH,
) -> tuple[
    HistoricalReferencePermissionPolicy,
    dict[str, OfficialBoundarySource],
    tuple[dict[str, str], ...],
]:
    """Load explicit approvals without fetching, changing, or inferring data."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Historical-reference permission configuration must be an object.")
    sources = _source_registry(payload.get("source_registry"))
    raw_rule = payload.get("approval_rule")
    if not isinstance(raw_rule, Mapping):
        raise ValueError("Historical-reference permission requires approval_rule.")
    raw_source_ids = raw_rule.get("required_sources")
    if not isinstance(raw_source_ids, list) or not raw_source_ids:
        raise ValueError("Historical-reference permission requires required_sources.")
    required_source_ids = tuple(
        _required_text(source_id, "required source ID") for source_id in raw_source_ids
    )
    if len(set(required_source_ids)) != len(required_source_ids):
        raise ValueError("Historical-reference permission required source IDs must be unique.")
    missing_sources = set(required_source_ids) - set(sources)
    if missing_sources:
        raise ValueError(
            "Historical-reference permission references unknown required source IDs: "
            f"{sorted(missing_sources)}."
        )
    permitted = raw_rule.get("permitted_features")
    prohibited = raw_rule.get("prohibited_features")
    if not isinstance(permitted, list) or not permitted:
        raise ValueError("Historical-reference permission requires permitted_features.")
    if not isinstance(prohibited, list) or not prohibited:
        raise ValueError("Historical-reference permission requires prohibited_features.")
    policy = HistoricalReferencePermissionPolicy(
        framework_id=_required_text(payload.get("framework_id"), "framework_id"),
        purpose=_required_text(payload.get("purpose"), "purpose"),
        required_crosswalk_status=_required_text(
            raw_rule.get("required_crosswalk_status"), "required_crosswalk_status"
        ),
        required_source_ids=required_source_ids,
        minimum_mutual_overlap_percentage=_required_number(
            raw_rule.get("minimum_mutual_overlap_percentage"),
            "minimum_mutual_overlap_percentage",
        ),
        maximum_competing_overlap_percentage=_required_number(
            raw_rule.get("maximum_competing_overlap_percentage"),
            "maximum_competing_overlap_percentage",
        ),
        permitted_features=tuple(_required_text(item, "permitted feature") for item in permitted),
        prohibited_features=tuple(_required_text(item, "prohibited feature") for item in prohibited),
        limitation=_required_text(raw_rule.get("limitation"), "limitation"),
    )
    if policy.required_crosswalk_status != DIRECT_STATUS:
        raise ValueError("Historical-reference permissions may only approve accepted_direct rows.")
    if policy.minimum_mutual_overlap_percentage < 0 or policy.maximum_competing_overlap_percentage < 0:
        raise ValueError("Historical-reference permission thresholds cannot be negative.")

    raw_approvals = payload.get("approved_mappings")
    if not isinstance(raw_approvals, list):
        raise ValueError("Historical-reference permission requires approved_mappings.")
    approvals: list[dict[str, str]] = []
    approval_ids: set[str] = set()
    required_mapping_fields = {
        "mapping_id",
        "previous_area_id",
        "previous_area_name",
        "current_election_id",
        "current_area_id",
        "current_area_name",
        "current_geometry_source_id",
    }
    for raw_approval in raw_approvals:
        if not isinstance(raw_approval, Mapping):
            raise ValueError("Historical-reference approval entries must be objects.")
        missing = required_mapping_fields - set(raw_approval)
        if missing:
            raise ValueError(
                "Historical-reference approval is missing required fields: "
                f"{sorted(missing)}."
            )
        approval = {
            field: _required_text(raw_approval.get(field), field)
            for field in required_mapping_fields
        }
        # The official election-result archive can use ``&`` while the ONS
        # boundary source spells the same verified division with ``and``.  An
        # optional explicit source label handles only this documented display
        # difference; it is not a name-similarity or geographic inference.
        if "historical_event_area_name" in raw_approval:
            approval["historical_event_area_name"] = _required_text(
                raw_approval.get("historical_event_area_name"),
                "historical_event_area_name",
            )
        if approval["mapping_id"] in approval_ids:
            raise ValueError(
                f"Duplicate historical-reference approval ID: {approval['mapping_id']}."
            )
        if approval["current_geometry_source_id"] not in sources:
            raise ValueError(
                "Historical-reference approval references an unknown current geometry source: "
                f"{approval['current_geometry_source_id']}."
            )
        approval_ids.add(approval["mapping_id"])
        approvals.append(approval)
    return policy, sources, tuple(approvals)


def _mutual_overlap_percentage(row: Mapping[str, object]) -> float:
    """Use the conservative smaller directional overlap from the verified GIS row."""

    values = (row.get("source_overlap_ratio"), row.get("target_overlap_ratio"))
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in values):
        raise ValueError("Accepted-direct crosswalk rows require numeric overlap ratios.")
    return min(float(value) for value in values) * 100


def _largest_competing_overlap_percentage(
    row: Mapping[str, object],
    all_rows: Sequence[Mapping[str, object]],
) -> float:
    """Measure a competing link without using it to select or merge an area."""

    current_key = (row.get("current_election_id"), row.get("current_area_id"))
    previous_id = row.get("previous_area_id")
    competitors = []
    for candidate in all_rows:
        same_current = (candidate.get("current_election_id"), candidate.get("current_area_id")) == current_key
        same_previous = candidate.get("previous_area_id") == previous_id
        if candidate is row or (same_current and same_previous):
            continue
        if same_current or same_previous:
            try:
                competitors.append(_mutual_overlap_percentage(candidate))
            except ValueError:
                continue
    return max(competitors, default=0.0)


def _assert_exact_mapping(approval: Mapping[str, str], row: Mapping[str, object]) -> None:
    """Ensure a configured approval cannot silently drift to another geography."""

    for field in (
        "mapping_id",
        "previous_area_id",
        "previous_area_name",
        "current_election_id",
        "current_area_id",
        "current_area_name",
    ):
        if approval[field] != row.get(field):
            raise ValueError(
                f"Historical-reference approval {approval['mapping_id']} does not match "
                f"the verified crosswalk field {field}."
            )


def build_historical_reference_permission_audit(
    crosswalk_rows: Sequence[Mapping[str, object]],
    *,
    configuration_path: str | Path = DEFAULT_PERMISSION_CONFIGURATION_PATH,
) -> dict[str, object]:
    """Create additive approval records from reviewed GIS and official evidence.

    An absent configuration approval is deliberately not an error: it produces
    ``insufficient_official_evidence`` and keeps all historical-reference
    fields unavailable.  A malformed or mismatched approval is an error,
    because silently approving a different boundary would be unsafe.
    """

    policy, sources, approvals = load_historical_reference_permission_configuration(
        configuration_path
    )
    direct_rows = [
        dict(row) for row in crosswalk_rows if row.get("analytical_status") == DIRECT_STATUS
    ]
    direct_by_id: dict[str, dict[str, object]] = {}
    for row in direct_rows:
        mapping_id = row.get("mapping_id")
        if not isinstance(mapping_id, str) or not mapping_id:
            raise ValueError("Accepted-direct crosswalk rows require mapping_id.")
        if mapping_id in direct_by_id:
            raise ValueError(f"Duplicate accepted-direct mapping ID: {mapping_id}.")
        direct_by_id[mapping_id] = row

    approval_by_id = {approval["mapping_id"]: approval for approval in approvals}
    records: list[HistoricalReferencePermissionRecord] = []
    for mapping_id, row in sorted(direct_by_id.items()):
        approval = approval_by_id.get(mapping_id)
        if approval is None:
            records.append(
                HistoricalReferencePermissionRecord(
                    mapping_id=mapping_id,
                    previous_election_id=row.get("previous_election_id") if isinstance(row.get("previous_election_id"), str) else None,
                    previous_area_id=_required_text(row.get("previous_area_id"), "previous_area_id"),
                    previous_area_name=_required_text(row.get("previous_area_name"), "previous_area_name"),
                    historical_event_area_name=_required_text(
                        row.get("previous_area_name"), "previous_area_name"
                    ),
                    current_election_id=_required_text(row.get("current_election_id"), "current_election_id"),
                    current_area_id=_required_text(row.get("current_area_id"), "current_area_id"),
                    current_area_name=_required_text(row.get("current_area_name"), "current_area_name"),
                    crosswalk_status=DIRECT_STATUS,
                    historical_reference_status=INSUFFICIENT_STATUS,
                    previous_winner_allowed=False,
                    candidate_history_allowed=False,
                    incumbency_allowed=False,
                    party_vote_share_change_allowed=False,
                    source_ids=(),
                    source_urls=(),
                    evidence_summary="No explicit official-boundary approval is configured for this accepted-direct relationship.",
                    uncertainty="Retain historical-reference fields as NULL until exact official evidence is recorded.",
                )
            )
            continue

        _assert_exact_mapping(approval, row)
        mutual_overlap = _mutual_overlap_percentage(row)
        # Check every retained relationship, not only other direct rows.  A
        # lower-status material competitor is still evidence that must prevent
        # this narrow approval from being granted automatically.
        competitor_overlap = _largest_competing_overlap_percentage(row, crosswalk_rows)
        if mutual_overlap < policy.minimum_mutual_overlap_percentage:
            raise ValueError(
                f"Historical-reference approval {mapping_id} fails the configured mutual-overlap threshold."
            )
        if competitor_overlap > policy.maximum_competing_overlap_percentage:
            raise ValueError(
                f"Historical-reference approval {mapping_id} has a competing overlap above the configured limit."
            )
        source_ids = (*policy.required_source_ids, approval["current_geometry_source_id"])
        source_urls = tuple(sources[source_id].source_url for source_id in source_ids)
        records.append(
            HistoricalReferencePermissionRecord(
                mapping_id=mapping_id,
                previous_election_id=row.get("previous_election_id") if isinstance(row.get("previous_election_id"), str) else None,
                previous_area_id=_required_text(row.get("previous_area_id"), "previous_area_id"),
                previous_area_name=_required_text(row.get("previous_area_name"), "previous_area_name"),
                historical_event_area_name=approval.get(
                    "historical_event_area_name",
                    _required_text(row.get("previous_area_name"), "previous_area_name"),
                ),
                current_election_id=_required_text(row.get("current_election_id"), "current_election_id"),
                current_area_id=_required_text(row.get("current_area_id"), "current_area_id"),
                current_area_name=_required_text(row.get("current_area_name"), "current_area_name"),
                crosswalk_status=DIRECT_STATUS,
                historical_reference_status=APPROVED_STATUS,
                previous_winner_allowed=True,
                # Boundary equivalence never identifies a person or transfers
                # an office.  These remain blocked even for approved areas.
                candidate_history_allowed=False,
                incumbency_allowed=False,
                party_vote_share_change_allowed=False,
                source_ids=source_ids,
                source_urls=source_urls,
                evidence_summary=(
                    "Exact accepted-direct GIS relationship satisfies the configured "
                    f"{policy.minimum_mutual_overlap_percentage:.1f}% mutual-overlap and "
                    f"{policy.maximum_competing_overlap_percentage:.1f}% competing-overlap limits, "
                    "with the cited official legal and boundary sources."
                ),
                uncertainty=policy.limitation,
            )
        )

    unexpected_approvals = set(approval_by_id) - set(direct_by_id)
    if unexpected_approvals:
        raise ValueError(
            "Historical-reference approvals must refer to existing accepted-direct crosswalk rows: "
            f"{sorted(unexpected_approvals)}."
        )
    return {
        "framework_id": policy.framework_id,
        "purpose": policy.purpose,
        "approval_rule": {
            "required_crosswalk_status": policy.required_crosswalk_status,
            "required_source_ids": list(policy.required_source_ids),
            "minimum_mutual_overlap_percentage": policy.minimum_mutual_overlap_percentage,
            "maximum_competing_overlap_percentage": policy.maximum_competing_overlap_percentage,
            "permitted_features": list(policy.permitted_features),
            "prohibited_features": list(policy.prohibited_features),
            "limitation": policy.limitation,
        },
        "source_registry": [asdict(source) for source in sources.values()],
        "permission_records": [asdict(record) for record in records],
        "summary": {
            "accepted_direct_relationships_reviewed": len(direct_rows),
            "approved_for_historical_reference": sum(
                record.historical_reference_status == APPROVED_STATUS for record in records
            ),
            "insufficient_official_evidence": sum(
                record.historical_reference_status == INSUFFICIENT_STATUS for record in records
            ),
            "other_crosswalk_relationships_retained_without_reclassification": len(crosswalk_rows)
            - len(direct_rows),
        },
    }


def permission_records_by_mapping_id(
    audit: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    """Index permission records without falling back to a ward-name comparison."""

    raw_records = audit.get("permission_records")
    if not isinstance(raw_records, list):
        raise ValueError("Historical-reference permission audit requires permission_records.")
    result: dict[str, dict[str, object]] = {}
    for record in raw_records:
        if not isinstance(record, Mapping) or not isinstance(record.get("mapping_id"), str):
            raise ValueError("Historical-reference permission records require mapping_id.")
        mapping_id = str(record["mapping_id"])
        if mapping_id in result:
            raise ValueError(f"Duplicate historical-reference permission record: {mapping_id}.")
        result[mapping_id] = dict(record)
    return result


def historical_reference_permission_markdown(audit: Mapping[str, object]) -> str:
    """Render a compact, citable review report without exposing source data."""

    records = audit.get("permission_records")
    summary = audit.get("summary")
    sources = audit.get("source_registry")
    if not isinstance(records, list) or not isinstance(summary, Mapping) or not isinstance(sources, list):
        raise ValueError("Historical-reference permission audit is incomplete.")
    lines = [
        "# Historic Surrey (2013–2021) to 2026 Historical Reference Permission Audit",
        "",
        "## Purpose",
        "",
        "This audit separately records whether an existing `accepted_direct` GIS relationship may be used as a limited analytical historical reference. It does not change election results, assert legal succession, or transfer candidate identity, incumbency, swing, or redistributed votes.",
        "",
        "## Result",
        "",
        f"- Accepted-direct relationships reviewed: {summary.get('accepted_direct_relationships_reviewed')}",
        f"- Approved for limited historical reference: {summary.get('approved_for_historical_reference')}",
        f"- Insufficient official evidence: {summary.get('insufficient_official_evidence')}",
        f"- Other retained crosswalk relationships, not reclassified: {summary.get('other_crosswalk_relationships_retained_without_reclassification')}",
        "",
        "Approved records may expose only the previous principal event, its source-reported winning candidate and party (without asserting identity continuity), source-reported turnout and electorate, source-reported winner vote share, observed contest size, and exact original-party history. Every other crosswalk status remains blocked. Candidate identity, incumbency, predecessor relationships, party vote-share change, swing, and vote redistribution remain unavailable for every record.",
        "",
        "## Official evidence registry",
        "",
    ]
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        lines.append(
            f"- [{source.get('source_id')}]({source.get('source_url')}): "
            f"{source.get('evidence_text')}"
        )
    lines.extend(
        [
            "",
            "## Exact mapping decisions",
            "",
            "| Boundary division | Configured historic lookup label | 2026 ward | Decision | Evidence sources | Limitation |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in records:
        if not isinstance(record, Mapping):
            continue
        source_ids = ", ".join(str(item) for item in record.get("source_ids", [])) or "None"
        lines.append(
            "| "
            f"{record.get('previous_area_name')} | {record.get('historical_event_area_name')} | {record.get('current_area_name')} | "
            f"`{record.get('historical_reference_status')}` | {source_ids} | "
            f"{record.get('uncertainty')} |"
        )
    lines.extend(
        [
            "",
            "## Boundary of this decision",
            "",
            "The 2026 Structural Changes Order links each 2026 ward to a same-named 2024 division. The 2024 Electoral Changes Order replaced the former divisions, so this audit does not treat a matching name as proof. Approval is granted only where the existing crosswalk contains one exact accepted-direct GIS relationship and the configured official legal and mapping evidence is retained. This is analytical geographic continuity, not a legal or personal identity claim.",
            "",
        ]
    )
    return "\n".join(lines)
