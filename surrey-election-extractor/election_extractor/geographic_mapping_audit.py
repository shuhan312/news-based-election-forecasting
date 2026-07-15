"""Audit evidence for historical Surrey geography to 2026 ward mapping.

This module deliberately distinguishes structural reorganisation evidence from
an authoritative area-to-area crosswalk.  It never creates mapping rows from
matching names, election years, candidate counts, or geographic assumptions.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from election_extractor.master_database import AuditedElectionInput


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_CONFIG_PATH = PROJECT_ROOT / "config/geographic_mapping_audit.json"


class GeographicMappingAuditStatus(str, Enum):
    """Describe whether reviewed sources justify writing any mapping rows."""

    REQUIRES_AUTHORITATIVE_CROSSWALK = "requires_authoritative_crosswalk"
    REFERENCE_BRIDGE_READY = "reference_bridge_ready"
    CROSSWALK_REVIEW_REQUIRED = "crosswalk_review_required"


@dataclass(frozen=True)
class MappingEvidenceSource:
    """Keep one reviewed source and its precise mapping capability."""

    source_name: str
    source_type: str
    source_url: str
    evidence_scope: str
    evidence_text: str
    # These three flags distinguish a legal 2026-to-2024 identity bridge from
    # the still-unavailable 2013/2017/2021-to-2026 crosswalk.  Treating them as
    # one generic "mapping source" would wrongly permit historical comparison.
    direct_historical_to_current_crosswalk_available: bool
    direct_current_to_reference_crosswalk_available: bool
    official_boundary_geometry_available: bool


@dataclass(frozen=True)
class GeographicMappingAuditConfiguration:
    """Identify the audited historical and 2026 election inputs explicitly."""

    audit_id: str
    previous_election_ids: tuple[str, ...]
    current_election_ids: tuple[str, ...]
    sources: tuple[MappingEvidenceSource, ...]


def _required_text(value: object, field_name: str) -> str:
    """Reject absent evidence metadata instead of silently inventing it."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Geographic mapping audit requires a non-empty {field_name}.")
    return value.strip()


def _identifiers(value: object, field_name: str) -> tuple[str, ...]:
    """Require distinct configured identifiers rather than selecting defaults."""

    if not isinstance(value, list) or not value:
        raise ValueError(f"Geographic mapping audit requires {field_name}.")
    identifiers = tuple(_required_text(item, field_name) for item in value)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"Geographic mapping audit has duplicate {field_name}.")
    return identifiers


def load_geographic_mapping_audit_configuration(
    path: str | Path = DEFAULT_AUDIT_CONFIG_PATH,
) -> GeographicMappingAuditConfiguration:
    """Load a reviewed source register without fetching or parsing web pages."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Geographic mapping audit configuration must be an object.")
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("Geographic mapping audit requires at least one source.")
    sources = []
    for item in raw_sources:
        if not isinstance(item, dict):
            raise ValueError("Geographic mapping audit source entries must be objects.")
        capabilities = {}
        for field_name in (
            "direct_historical_to_current_crosswalk_available",
            "direct_current_to_reference_crosswalk_available",
            "official_boundary_geometry_available",
        ):
            value = item.get(field_name)
            if not isinstance(value, bool):
                raise ValueError(
                    "Geographic mapping audit source entries require a boolean "
                    f"{field_name}."
                )
            capabilities[field_name] = value
        sources.append(
            MappingEvidenceSource(
                source_name=_required_text(item.get("source_name"), "source_name"),
                source_type=_required_text(item.get("source_type"), "source_type"),
                source_url=_required_text(item.get("source_url"), "source_url"),
                evidence_scope=_required_text(item.get("evidence_scope"), "evidence_scope"),
                evidence_text=_required_text(item.get("evidence_text"), "evidence_text"),
                **capabilities,
            )
        )
    return GeographicMappingAuditConfiguration(
        audit_id=_required_text(payload.get("audit_id"), "audit_id"),
        previous_election_ids=_identifiers(
            payload.get("previous_election_ids"),
            "previous_election_ids",
        ),
        current_election_ids=_identifiers(
            payload.get("current_election_ids"),
            "current_election_ids",
        ),
        sources=tuple(sources),
    )


def _coverage_row(election: AuditedElectionInput) -> dict[str, object]:
    """Summarise one audited geography without declaring it comparable to another."""

    source_urls = {record.source_url for record in election.records}
    names = {record.division_ward_name for record in election.records}
    return {
        "election_id": election.configuration.election_id,
        "election_name": election.configuration.election_name,
        "election_year": election.configuration.election_year,
        "election_type": election.configuration.election_type,
        "official_election_url": election.configuration.official_url,
        "source_audit": str(election.audit_path),
        "area_count": len(source_urls),
        "published_area_name_count": len(names - {None}),
        "candidate_record_count": len(election.records),
    }


def build_geographic_mapping_audit(
    elections: Sequence[AuditedElectionInput],
    configuration: GeographicMappingAuditConfiguration,
) -> dict[str, object]:
    """Produce a read-only audit of whether mapping evidence is available.

    No result-page names are compared or matched here.  Shared words such as
    "Ash" or "Guildford" are not geographical evidence, and therefore cannot
    create a direct mapping, confidence value or historical comparison.
    """

    elections_by_id = {
        election.configuration.election_id: election for election in elections
    }
    required_ids = (
        *configuration.previous_election_ids,
        *configuration.current_election_ids,
    )
    missing_ids = [election_id for election_id in required_ids if election_id not in elections_by_id]
    if missing_ids:
        raise ValueError(
            "Geographic mapping audit is missing configured elections: "
            + ", ".join(missing_ids)
        )

    has_historical_crosswalk = any(
        source.direct_historical_to_current_crosswalk_available
        for source in configuration.sources
    )
    has_reference_bridge = any(
        source.direct_current_to_reference_crosswalk_available
        for source in configuration.sources
    )
    # A spatial candidate crosswalk can be assessed only when both the old
    # historic geometry and the legally referenced 2024 geometry are available.
    geometry_sources = sum(
        source.official_boundary_geometry_available for source in configuration.sources
    )
    status = (
        GeographicMappingAuditStatus.CROSSWALK_REVIEW_REQUIRED
        if has_historical_crosswalk
        else (
            GeographicMappingAuditStatus.REFERENCE_BRIDGE_READY
            if has_reference_bridge and geometry_sources >= 2
            else GeographicMappingAuditStatus.REQUIRES_AUTHORITATIVE_CROSSWALK
        )
    )
    return {
        "audit_id": configuration.audit_id,
        "status": status.value,
        "previous_election_coverage": [
            _coverage_row(elections_by_id[election_id])
            for election_id in configuration.previous_election_ids
        ],
        "current_election_coverage": [
            _coverage_row(elections_by_id[election_id])
            for election_id in configuration.current_election_ids
        ],
        "evidence_sources": [asdict(source) for source in configuration.sources],
        # This is intentionally a separate audit output.  The master database
        # Geographic Mapping table is not modified until a later reviewed
        # process records a specific previous/current pair with direct evidence.
        "verified_geographic_mapping_rows": [],
        "assessment": {
            "direct_historical_to_2026_crosswalk_available": has_historical_crosswalk,
            "official_2026_to_2024_reference_bridge_available": has_reference_bridge,
            "official_boundary_geometry_source_count": geometry_sources,
            "historical_comparisons_allowed": False,
            "prohibited_inferences": [
                "Do not map areas by similar names.",
                "Do not map areas from the shared 2026 election year.",
                "Do not map areas from candidate counts, seat counts or elected candidates.",
                "Do not calculate vote change, previous winner, incumbency or candidate history.",
            ],
            "next_required_evidence": (
                "A reviewed GIS-overlay crosswalk, based on the official historical "
                "division geometry and the official 2024 geometry, that records each "
                "specific historical division/current ward overlap and source evidence."
            ),
        },
    }


def audit_markdown(audit: Mapping[str, Any]) -> str:
    """Render a concise report without adding any geographic mapping claims."""

    previous = audit["previous_election_coverage"]
    current = audit["current_election_coverage"]
    sources = audit["evidence_sources"]
    assert isinstance(previous, list) and isinstance(current, list) and isinstance(sources, list)
    assessment = audit["assessment"]
    assert isinstance(assessment, Mapping)
    lines = [
        "# Surrey Historical-to-2026 Geographic Mapping Evidence Audit",
        "",
        f"- Audit status: `{audit['status']}`",
        f"- Verified Geographic Mapping rows created: {len(audit['verified_geographic_mapping_rows'])}",
        f"- Historical comparisons allowed: {assessment['historical_comparisons_allowed']}",
        "",
        "## Historical election coverage",
        "",
    ]
    for item in previous:
        assert isinstance(item, Mapping)
        lines.append(
            "- {election_id}: {area_count} published divisions/areas; "
            "{candidate_record_count} candidate records.".format(**item)
        )
    lines.extend(["", "## 2026 election coverage", ""])
    for item in current:
        assert isinstance(item, Mapping)
        lines.append(
            "- {election_id}: {area_count} published wards/areas; "
            "{candidate_record_count} candidate records.".format(**item)
        )
    lines.extend(["", "## Reviewed evidence", ""])
    for source in sources:
        assert isinstance(source, Mapping)
        lines.append(
            "- [{source_name}]({source_url}) — {evidence_text} "
            "Historical crosswalk: `{direct_historical_to_current_crosswalk_available}`; "
            "2026-to-2024 bridge: `{direct_current_to_reference_crosswalk_available}`; "
            "official geometry: `{official_boundary_geometry_available}`.".format(
                **source
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "The 2026 Order provides an official legal bridge from each 2026 ward to a same-area 2024 electoral division. It does not identify an individual 2013, 2017 or 2021 division as the same geography as a 2026 ward. Therefore no historical Geographic Mapping rows have been written and no historical comparison or enrichment is permitted.",
            "",
            "## Required next evidence",
            "",
            str(assessment["next_required_evidence"]),
            "",
        ]
    )
    return "\n".join(lines)
