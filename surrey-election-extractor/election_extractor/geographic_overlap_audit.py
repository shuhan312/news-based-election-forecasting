"""Create reviewable GIS overlap candidates without creating geographic mappings.

The output of this module is deliberately evidence for human review.  A spatial
intersection is not, by itself, proof that an old division and a 2026 ward are
analytically equivalent.  Therefore this module never writes the master
database's ``Geographic Mapping`` table and never calculates electoral change.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERLAP_CONFIG_PATH = PROJECT_ROOT / "config/geographic_overlap_audit.json"
MINIMUM_REVIEWABLE_INTERSECTION_SQUARE_METRES = 1.0


@dataclass(frozen=True)
class BoundarySource:
    """Describe one public GIS source and its published feature identifiers."""

    source_name: str
    source_url: str
    name_field: str
    identifier_field: str
    election_id: str | None = None


@dataclass(frozen=True)
class OverlapAuditConfiguration:
    """Keep all spatial-input provenance explicit and reproducible."""

    audit_id: str
    coordinate_reference_system: str
    minimum_reviewable_intersection_square_metres: float
    historical_source: BoundarySource
    current_sources: tuple[BoundarySource, ...]
    legal_2026_source_name: str
    legal_2026_source_url: str
    legal_2026_evidence_text: str


@dataclass(frozen=True)
class BoundaryArea:
    """One named official boundary feature in a known coordinate reference system."""

    area_name: str
    area_identifier: str
    geometry: BaseGeometry
    source_url: str
    election_id: str | None = None


@dataclass(frozen=True)
class SpatialOverlapCandidate:
    """One unapproved historical-division to 2026-ward spatial intersection."""

    previous_area_name: str
    previous_area_id: str
    current_election_id: str
    current_area_name: str
    current_area_id: str
    intersection_area_square_metres: float
    previous_area_overlap_percent: float
    current_area_overlap_percent: float
    mapping_type: str
    review_status: str
    previous_geometry_source_url: str
    current_geometry_source_url: str
    notes: str


def _required_text(value: object, field_name: str) -> str:
    """Reject incomplete source configuration instead of silently selecting defaults."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Geographic overlap audit requires a non-empty {field_name}.")
    return value.strip()


def _valid_url(value: object, field_name: str) -> str:
    """Require an explicit public HTTP(S) source URL for every GIS dataset."""

    url = _required_text(value, field_name)
    if not url.startswith(("https://", "http://")):
        raise ValueError(f"Geographic overlap audit requires a HTTP(S) {field_name}.")
    return url


def _load_boundary_source(payload: object, *, requires_election_id: bool) -> BoundarySource:
    """Validate one configured source before any network request is attempted."""

    if not isinstance(payload, dict):
        raise ValueError("Geographic overlap audit boundary sources must be objects.")
    election_id = payload.get("election_id")
    if requires_election_id:
        election_id = _required_text(election_id, "election_id")
    elif election_id is not None:
        raise ValueError("Historical GIS source must not define an election_id.")
    return BoundarySource(
        source_name=_required_text(payload.get("source_name"), "source_name"),
        source_url=_valid_url(payload.get("source_url"), "source_url"),
        name_field=_required_text(payload.get("name_field"), "name_field"),
        identifier_field=_required_text(payload.get("identifier_field"), "identifier_field"),
        election_id=election_id if isinstance(election_id, str) else None,
    )


def load_overlap_audit_configuration(
    path: str | Path = DEFAULT_OVERLAP_CONFIG_PATH,
) -> OverlapAuditConfiguration:
    """Load source metadata only; this function does not fetch boundary data."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Geographic overlap audit configuration must be an object.")
    current_payload = payload.get("current_sources")
    if not isinstance(current_payload, list) or not current_payload:
        raise ValueError("Geographic overlap audit requires current_sources.")
    current_sources = tuple(
        _load_boundary_source(item, requires_election_id=True) for item in current_payload
    )
    current_ids = [source.election_id for source in current_sources]
    if len(current_ids) != len(set(current_ids)):
        raise ValueError("Geographic overlap audit has duplicate current election IDs.")
    legal_source = payload.get("legal_2026_source")
    if not isinstance(legal_source, dict):
        raise ValueError("Geographic overlap audit requires legal_2026_source.")
    minimum_intersection = payload.get("minimum_reviewable_intersection_square_metres")
    if not isinstance(minimum_intersection, (int, float)) or isinstance(minimum_intersection, bool):
        raise ValueError(
            "Geographic overlap audit requires a numeric "
            "minimum_reviewable_intersection_square_metres."
        )
    if minimum_intersection <= 0:
        raise ValueError(
            "Geographic overlap audit minimum_reviewable_intersection_square_metres "
            "must be greater than zero."
        )
    return OverlapAuditConfiguration(
        audit_id=_required_text(payload.get("audit_id"), "audit_id"),
        coordinate_reference_system=_required_text(
            payload.get("coordinate_reference_system"),
            "coordinate_reference_system",
        ),
        minimum_reviewable_intersection_square_metres=float(minimum_intersection),
        historical_source=_load_boundary_source(
            payload.get("historical_source"),
            requires_election_id=False,
        ),
        current_sources=current_sources,
        legal_2026_source_name=_required_text(
            legal_source.get("source_name"),
            "legal_2026_source.source_name",
        ),
        legal_2026_source_url=_valid_url(
            legal_source.get("source_url"),
            "legal_2026_source.source_url",
        ),
        legal_2026_evidence_text=_required_text(
            legal_source.get("evidence_text"),
            "legal_2026_source.evidence_text",
        ),
    )


def fetch_public_geojson(source: BoundarySource, *, timeout_seconds: int = 30) -> dict[str, object]:
    """Download a public GIS response without credentials, scraping or browser automation."""

    request = Request(
        source.source_url,
        headers={"User-Agent": "SurreyElectionExtractor/1.0 (research audit)"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL is config-validated.
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{source.source_name} did not return a JSON object.")
    return payload


def boundary_areas_from_geojson(
    payload: Mapping[str, object],
    source: BoundarySource,
) -> tuple[BoundaryArea, ...]:
    """Parse official GeoJSON while retaining published names and identifiers exactly."""

    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"{source.source_name} must return a GeoJSON FeatureCollection.")
    raw_features = payload.get("features")
    if not isinstance(raw_features, list) or not raw_features:
        raise ValueError(f"{source.source_name} did not provide any boundary features.")

    areas: list[BoundaryArea] = []
    identifiers: set[str] = set()
    for index, feature in enumerate(raw_features, start=1):
        if not isinstance(feature, dict):
            raise ValueError(f"{source.source_name} feature {index} is not an object.")
        properties = feature.get("properties")
        geometry_payload = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry_payload, dict):
            raise ValueError(f"{source.source_name} feature {index} has no geometry or properties.")
        name = _required_text(properties.get(source.name_field), f"feature {index} name")
        identifier = _required_text(
            properties.get(source.identifier_field),
            f"feature {index} identifier",
        )
        if identifier in identifiers:
            raise ValueError(f"{source.source_name} has duplicate identifier {identifier!r}.")
        geometry = shape(geometry_payload)
        if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
            raise ValueError(f"{source.source_name} feature {identifier!r} has invalid geometry.")
        identifiers.add(identifier)
        areas.append(
            BoundaryArea(
                area_name=name,
                area_identifier=identifier,
                geometry=geometry,
                source_url=source.source_url,
                election_id=source.election_id,
            )
        )
    return tuple(areas)


def calculate_spatial_overlap_candidates(
    historical_areas: Sequence[BoundaryArea],
    current_areas: Sequence[BoundaryArea],
    *,
    minimum_intersection_square_metres: float = MINIMUM_REVIEWABLE_INTERSECTION_SQUARE_METRES,
) -> tuple[SpatialOverlapCandidate, ...]:
    """Calculate all non-zero intersections without selecting a 'winning' mapping.

    The function intentionally reports every reviewable overlap. Selecting only
    the largest percentage would turn an automated spatial calculation into an
    unsupported claim that a historical division is equivalent to one current
    ward. Intersections below the stated one-square-metre precision tolerance
    are boundary-contact artefacts, not meaningful area overlaps.
    """

    if minimum_intersection_square_metres <= 0:
        raise ValueError("minimum_intersection_square_metres must be greater than zero.")
    candidates: list[SpatialOverlapCandidate] = []
    for historical in historical_areas:
        for current in current_areas:
            if current.election_id is None:
                raise ValueError("Current GIS areas require an election_id.")
            intersection = historical.geometry.intersection(current.geometry)
            intersection_area = intersection.area
            # Adjacent polygons can return sub-square-metre floating-point slivers.
            # Retaining them would create false crosswalk candidates, so the
            # configured precision tolerance is recorded in every audit report.
            if intersection.is_empty or intersection_area < minimum_intersection_square_metres:
                continue
            candidates.append(
                SpatialOverlapCandidate(
                    previous_area_name=historical.area_name,
                    previous_area_id=historical.area_identifier,
                    current_election_id=current.election_id,
                    current_area_name=current.area_name,
                    current_area_id=current.area_identifier,
                    intersection_area_square_metres=round(intersection_area, 3),
                    previous_area_overlap_percent=round(
                        intersection_area / historical.geometry.area * 100,
                        6,
                    ),
                    current_area_overlap_percent=round(
                        intersection_area / current.geometry.area * 100,
                        6,
                    ),
                    mapping_type="official_gis_spatial_overlap_candidate",
                    review_status="requires_manual_review",
                    previous_geometry_source_url=historical.source_url,
                    current_geometry_source_url=current.source_url,
                    notes=(
                        "Spatial intersection is an evidence candidate only. "
                        "It is not a final geographic equivalence or a basis for "
                        "historical vote comparison until manually reviewed."
                    ),
                )
            )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.previous_area_name.casefold(),
                -item.previous_area_overlap_percent,
                item.current_election_id,
                item.current_area_name.casefold(),
            ),
        )
    )


def build_geographic_overlap_audit(
    configuration: OverlapAuditConfiguration,
    historical_areas: Sequence[BoundaryArea],
    current_areas: Sequence[BoundaryArea],
) -> dict[str, object]:
    """Build an auditable report that keeps candidate and final mappings separate."""

    if not historical_areas or not current_areas:
        raise ValueError("Geographic overlap audit requires historical and current areas.")
    candidates = calculate_spatial_overlap_candidates(
        historical_areas,
        current_areas,
        minimum_intersection_square_metres=(
            configuration.minimum_reviewable_intersection_square_metres
        ),
    )
    represented_historical = {candidate.previous_area_id for candidate in candidates}
    represented_current = {
        (candidate.current_election_id, candidate.current_area_id) for candidate in candidates
    }
    return {
        "audit_id": configuration.audit_id,
        "status": "manual_review_required",
        "coordinate_reference_system": configuration.coordinate_reference_system,
        "minimum_reviewable_intersection_square_metres": (
            configuration.minimum_reviewable_intersection_square_metres
        ),
        "historical_source": asdict(configuration.historical_source),
        "current_sources": [asdict(source) for source in configuration.current_sources],
        "legal_2026_source": {
            "source_name": configuration.legal_2026_source_name,
            "source_url": configuration.legal_2026_source_url,
            "evidence_text": configuration.legal_2026_evidence_text,
        },
        "coverage": {
            "historical_areas_loaded": len(historical_areas),
            "current_areas_loaded": len(current_areas),
            "historical_areas_with_non_zero_overlap": len(represented_historical),
            "current_areas_with_non_zero_overlap": len(represented_current),
            "candidate_overlap_rows": len(candidates),
        },
        "candidate_overlap_rows": [asdict(candidate) for candidate in candidates],
        # The empty list is intentional. This audit offers inputs for review; it
        # must not silently populate the master database's final mapping table.
        "verified_geographic_mapping_rows": [],
        "assessment": {
            "historical_comparisons_allowed": False,
            "automatic_mapping_created": False,
            "next_step": (
                "Review each candidate overlap against official boundary evidence "
                "before separately approving any Geographic Mapping row."
            ),
            "prohibited_uses": [
                "Do not choose the largest overlap as an automatic mapping.",
                "Do not calculate vote change, incumbency or candidate history.",
                "Do not treat a shared name as geographic evidence.",
            ],
        },
    }


def geographic_overlap_markdown(audit: Mapping[str, Any]) -> str:
    """Render a concise human-review report from the generated evidence."""

    coverage = audit["coverage"]
    assert isinstance(coverage, Mapping)
    assessment = audit["assessment"]
    assert isinstance(assessment, Mapping)
    rows = audit["candidate_overlap_rows"]
    assert isinstance(rows, list)
    lines = [
        "# Surrey Historical Division to 2026 Ward Spatial Overlap Audit",
        "",
        f"- Status: `{audit['status']}`",
        f"- Coordinate reference system: `{audit['coordinate_reference_system']}`",
        "- Minimum reviewable intersection: "
        f"{audit['minimum_reviewable_intersection_square_metres']} m²",
        f"- Historical areas loaded: {coverage['historical_areas_loaded']}",
        f"- 2026 wards loaded: {coverage['current_areas_loaded']}",
        f"- Candidate overlap rows: {coverage['candidate_overlap_rows']}",
        "- Final Geographic Mapping rows created: 0",
        f"- Historical comparisons allowed: {assessment['historical_comparisons_allowed']}",
        "",
        "## Method and boundary",
        "",
        "This report intersects official historical division geometry with official "
        "2026 East and West ward geometry in EPSG:27700. Every non-zero spatial "
        "intersection of at least the stated precision threshold is retained for review. "
        "It does not select a single target ward, "
        "declare equivalence, or alter the master database.",
        "",
        "## Candidate overlaps requiring review",
        "",
        "| Previous division | 2026 election | 2026 ward | Previous-area overlap | Current-area overlap | Review status |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in rows:
        assert isinstance(row, Mapping)
        lines.append(
            "| {previous_area_name} | {current_election_id} | {current_area_name} | "
            "{previous_area_overlap_percent:.3f}% | {current_area_overlap_percent:.3f}% | "
            "{review_status} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Required follow-up",
            "",
            str(assessment["next_step"]),
            "",
            "No vote change, previous winner, incumbency, candidate history or final "
            "geographic mapping has been calculated from these candidate rows.",
            "",
        ]
    )
    return "\n".join(lines)
