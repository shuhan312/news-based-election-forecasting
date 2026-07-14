"""Provider-neutral models used by the election-area discovery stage."""

from dataclasses import dataclass
from enum import Enum


class DiscoveryStatus(str, Enum):
    """Describe how much indexed evidence was available for one result URL."""

    DISCOVERED = "discovered"
    MISSING_AREA_NAME = "missing_area_name"
    MISSING_ELECTION_METADATA = "missing_election_metadata"


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


@dataclass(frozen=True)
class DiscoveryReport:
    """Return discovered areas together with the complete search audit."""

    source_index_url: str
    areas: tuple[DiscoveredElectionArea, ...]
    search_attempts: tuple[SearchAttempt, ...]
