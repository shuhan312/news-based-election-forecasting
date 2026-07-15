"""Provider-neutral models used by the election-area discovery stage."""

from dataclasses import dataclass
from enum import Enum


class DiscoveryStatus(str, Enum):
    """Describe how much indexed evidence was available for one result URL."""

    DISCOVERED = "discovered"
    MISSING_AREA_NAME = "missing_area_name"


class MetadataStatus(str, Enum):
    """Describe whether published election metadata accompanies a result URL."""

    COMPLETE = "complete"
    MISSING = "missing"


class AreaNameStatus(str, Enum):
    """Describe whether search and official ward names agree."""

    EXACT = "exact"
    SEARCH_ONLY = "search_only"
    OFFICIAL_ONLY = "official_only"
    NAME_MISMATCH = "name_mismatch"


@dataclass(frozen=True)
class SearchResult:
    """Represent one provider-neutral indexed search result."""

    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True)
class SearchAttempt:
    """Record one search request without storing credentials."""

    query: str
    source_index_url: str
    status: str
    result_count: int
    error: str | None = None


@dataclass(frozen=True)
class DiscoveredElectionArea:
    """Store one distinct official ward or division result URL."""

    election_year: int | None
    election_name: str | None
    division_ward_name: str | None
    result_url: str
    source_index_url: str
    discovery_status: DiscoveryStatus
    # These optional fields preserve both sides of a lightweight name check.
    # division_ward_name remains the extraction-compatible primary name.
    discovered_name: str | None = None
    official_name: str | None = None
    name_status: AreaNameStatus = AreaNameStatus.SEARCH_ONLY
    discovery_method: str = "indexed_search"
    official_index_url: str | None = None
    # Link validity and metadata availability are separate facts. An official
    # published result URL remains usable when its surrounding index omits the
    # election name or year; those absent fields are retained explicitly.
    metadata_status: MetadataStatus = MetadataStatus.COMPLETE
    missing_metadata_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiscoveryReport:
    """Return discovered areas together with the complete search audit."""

    source_index_url: str
    areas: tuple[DiscoveredElectionArea, ...]
    search_attempts: tuple[SearchAttempt, ...]


@dataclass(frozen=True)
class ElectionStructureMetadata:
    """Keep secondary election-structure evidence separate from official results.

    The two Seats fields are intentionally independent.  In particular, a
    secondary value is never a fallback for ``official_number_of_seats``.
    """

    election_year: int | None
    election_name: str | None
    authority: str | None
    division_or_ward_name: str
    official_number_of_seats: int | None
    secondary_number_of_seats: int | None
    seat_source_type: str | None = None
    seat_source_url: str | None = None
    seat_evidence_text: str | None = None
    confidence: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        """Require provenance whenever a secondary Seats value is recorded."""
        if self.secondary_number_of_seats is None:
            return

        provenance = {
            "seat_source_type": self.seat_source_type,
            "seat_source_url": self.seat_source_url,
            "seat_evidence_text": self.seat_evidence_text,
        }
        missing = [
            field_name
            for field_name, value in provenance.items()
            if value is None or not value.strip()
        ]
        if missing:
            raise ValueError(
                "Secondary Seats metadata requires source provenance: "
                + ", ".join(missing)
            )
