"""Provider-neutral models used across Surrey election pipeline stages."""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from urllib.parse import urlparse


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
    seat_source_name: str | None = None
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


class GeographicLevel(str, Enum):
    """Limit supplementary evidence to an explicit analytical scope."""

    ELECTION = "election"
    DIVISION = "division"
    CANDIDATE = "candidate"


class SupplementaryValidationStatus(str, Enum):
    """State whether an external evidence record passed the project review."""

    VERIFIED = "verified"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class DerivedValidationStatus(str, Enum):
    """State whether a calculated record passed its official-input checks."""

    VERIFIED = "verified"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


@dataclass(frozen=True)
class DerivedInput:
    """Identify one published official value used in a documented calculation."""

    field_name: str
    value: int

    def __post_init__(self) -> None:
        """Keep derivation inputs numeric and explicitly named."""

        if not self.field_name.strip():
            raise ValueError("Derived input field_name cannot be blank.")
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise ValueError("Derived input values must be integers.")


@dataclass(frozen=True)
class DerivedMetadataRecord:
    """Store a transparent calculation without changing an official field.

    This layer is intentionally distinct from both official extraction and
    supplementary-source evidence.  Its value is a reproducible calculation
    from named values on one official result page, not a value that the page
    itself published.
    """

    metadata_id: str
    election_id: str
    division_id: str
    field_name: str
    target_official_field: str
    value: int
    geographic_level: GeographicLevel
    formula: str
    inputs: tuple[DerivedInput, ...]
    source_url: str
    evidence_text: str
    retrieval_date: str
    confidence: str
    notes: str | None
    validation_status: DerivedValidationStatus

    def __post_init__(self) -> None:
        """Reject untraceable or ambiguously scoped calculated values."""

        required_text = {
            "metadata_id": self.metadata_id,
            "election_id": self.election_id,
            "division_id": self.division_id,
            "field_name": self.field_name,
            "target_official_field": self.target_official_field,
            "formula": self.formula,
            "source_url": self.source_url,
            "evidence_text": self.evidence_text,
            "retrieval_date": self.retrieval_date,
            "confidence": self.confidence,
        }
        missing = [name for name, value in required_text.items() if not value.strip()]
        if missing:
            raise ValueError("Derived metadata requires: " + ", ".join(missing))
        if self.geographic_level is not GeographicLevel.DIVISION:
            raise ValueError("Derived metadata is currently limited to division scope.")
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise ValueError("Derived metadata value must be an integer.")
        if self.value < 0:
            raise ValueError("Derived metadata value cannot be negative.")
        if not self.inputs:
            raise ValueError("Derived metadata requires at least one official input.")
        input_names = [item.field_name for item in self.inputs]
        if len(input_names) != len(set(input_names)):
            raise ValueError("Derived metadata input fields must be unique.")

        parsed_url = urlparse(self.source_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("Derived metadata source_url must be an HTTP(S) URL.")
        try:
            date.fromisoformat(self.retrieval_date)
        except ValueError as exc:
            raise ValueError(
                "Derived metadata retrieval_date must use YYYY-MM-DD."
            ) from exc


@dataclass(frozen=True)
class SupplementaryMetadataRecord:
    """Store one external evidence claim without changing official result data.

    ``value`` deliberately has no mapping to an official candidate or division
    field. Consumers must use this record as a separate provenance layer rather
    than treating it as a fallback for missing official values. Candidate-level
    evidence is additionally anchored to the exact published candidate name in
    the same official division result; this is a source-location check, not a
    claim that equally named candidates are the same person elsewhere.
    """

    metadata_id: str
    election_id: str
    division_id: str | None
    field_name: str
    value: object
    geographic_level: GeographicLevel
    source_type: str
    source_name: str
    source_url: str
    evidence_text: str
    retrieval_date: str
    confidence: str
    notes: str | None
    validation_status: SupplementaryValidationStatus
    candidate_name: str | None = None

    def __post_init__(self) -> None:
        """Reject untraceable or incorrectly scoped supplementary claims."""

        required_text = {
            "metadata_id": self.metadata_id,
            "election_id": self.election_id,
            "field_name": self.field_name,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "evidence_text": self.evidence_text,
            "retrieval_date": self.retrieval_date,
            "confidence": self.confidence,
        }
        missing = [name for name, value in required_text.items() if not value.strip()]
        if missing:
            raise ValueError(
                "Supplementary metadata requires: " + ", ".join(missing)
            )
        if self.value is None:
            raise ValueError("Supplementary metadata value cannot be null.")
        if self.geographic_level in {GeographicLevel.DIVISION, GeographicLevel.CANDIDATE} and not self.division_id:
            raise ValueError(
                "Division-level and candidate-level supplementary metadata require division_id."
            )
        if self.geographic_level is GeographicLevel.ELECTION and self.division_id:
            raise ValueError("Election-level supplementary metadata cannot have division_id.")
        if self.geographic_level is GeographicLevel.CANDIDATE and not (
            self.candidate_name and self.candidate_name.strip()
        ):
            raise ValueError("Candidate-level supplementary metadata requires candidate_name.")
        if self.geographic_level is not GeographicLevel.CANDIDATE and (
            self.candidate_name and self.candidate_name.strip()
        ):
            raise ValueError("Only candidate-level supplementary metadata may have candidate_name.")

        parsed_url = urlparse(self.source_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("Supplementary metadata source_url must be an HTTP(S) URL.")
        try:
            date.fromisoformat(self.retrieval_date)
        except ValueError as exc:
            raise ValueError(
                "Supplementary metadata retrieval_date must use YYYY-MM-DD."
            ) from exc
