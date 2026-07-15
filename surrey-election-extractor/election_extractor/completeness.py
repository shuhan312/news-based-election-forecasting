"""Assess election, division, and candidate completeness without changing source data."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from election_extractor.election_config import ElectionConfiguration
from election_extractor.extraction import CandidateResultRecord


class CompletenessStatus(str, Enum):
    """Describe whether all fields required for one data layer are present."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class MetadataSource(str, Enum):
    """Identify the provenance layer selected for a completeness assessment."""

    CONFIGURATION = "configuration"
    OFFICIAL = "official"
    SUPPLEMENTARY = "supplementary"
    MISSING = "missing"


@dataclass(frozen=True)
class SupplementaryMetadataValue:
    """Hold an optional secondary value without replacing an official value."""

    value: object
    source_reference: str


@dataclass(frozen=True)
class FieldCompleteness:
    """Record one field's availability and the source layer used to assess it."""

    field_name: str
    value: object | None
    source: MetadataSource
    source_reference: str | None
    note: str | None = None

    @property
    def complete(self) -> bool:
        """Treat only a non-empty published or configured value as available."""
        return _present(self.value)


@dataclass(frozen=True)
class ElectionCompleteness:
    """Summarise metadata completeness for one configured election."""

    election_id: str
    status: CompletenessStatus
    fields: tuple[FieldCompleteness, ...]
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class DivisionCompleteness:
    """Summarise official division and Voting Summary availability for one URL."""

    division_ward_name: str | None
    source_url: str
    status: CompletenessStatus
    fields: tuple[FieldCompleteness, ...]
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class CandidateCompleteness:
    """Summarise result-field availability for one already extracted candidate."""

    candidate_name: str
    source_url: str
    status: CompletenessStatus
    fields: tuple[FieldCompleteness, ...]
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class LayeredCompletenessReport:
    """Keep the three completeness layers separate and read-only."""

    election: ElectionCompleteness
    divisions: tuple[DivisionCompleteness, ...]
    candidates: tuple[CandidateCompleteness, ...]


ELECTION_FIELDS = ("election_name", "election_date", "election_type", "authority")
DIVISION_FIELDS = (
    ("division_ward_name", "division_ward_name"),
    ("number_of_seats", "number_of_seats"),
    ("electorate", "electorate"),
    ("ballot_papers_issued", "ballot_papers_issued"),
    ("ballot_papers_rejected", "ballot_papers_rejected"),
    ("turnout", "turnout"),
)
CANDIDATE_FIELDS = (
    ("candidate_name", "candidate_name"),
    ("original_party_name", "original_party_name"),
    ("votes_received", "votes_received"),
    ("vote_share", "vote_share"),
    # Surrey publishes this as an Outcome column. It is the evidence-backed
    # elected-status field; the optional duplicate ``elected`` property is not
    # separately required for candidate completeness.
    ("elected_status", "outcome"),
)


def _present(value: object | None) -> bool:
    """Recognise null and blank values as unavailable without converting them."""
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _status(fields: Sequence[FieldCompleteness]) -> tuple[CompletenessStatus, tuple[str, ...]]:
    """Derive one layer status from its own fields only."""
    missing = tuple(field.field_name for field in fields if not field.complete)
    status = CompletenessStatus.COMPLETE if not missing else CompletenessStatus.INCOMPLETE
    return status, missing


def _official_consensus(
    field_name: str,
    records: Sequence[CandidateResultRecord],
) -> FieldCompleteness:
    """Use one official value only when all available values agree.

    Conflicting values remain unavailable for completeness purposes. This avoids
    selecting a preferred result-page value or repairing the extracted records.
    """
    values = []
    source_urls = []
    for record in records:
        value = getattr(record, field_name)
        if _present(value):
            values.append(value)
            source_urls.append(record.source_url)

    distinct = list(dict.fromkeys(values))
    if len(distinct) == 1:
        references = tuple(dict.fromkeys(source_urls))
        reference = references[0] if len(references) == 1 else f"{len(references)} official result pages"
        return FieldCompleteness(field_name, distinct[0], MetadataSource.OFFICIAL, reference)
    if len(distinct) > 1:
        return FieldCompleteness(
            field_name,
            None,
            MetadataSource.MISSING,
            None,
            "Conflicting official values are retained in extraction evidence; no value was selected.",
        )
    return FieldCompleteness(
        field_name,
        None,
        MetadataSource.MISSING,
        None,
        "No value was published by the available official source.",
    )


def _configuration_values(configuration: ElectionConfiguration) -> dict[str, object]:
    """Expose only fields actually carried by the validated configuration."""
    return {
        "election_name": configuration.election_name,
        "election_type": configuration.election_type,
    }


def _election_field(
    field_name: str,
    configuration: ElectionConfiguration,
    records: Sequence[CandidateResultRecord],
    supplementary_metadata: Mapping[str, SupplementaryMetadataValue],
) -> FieldCompleteness:
    """Apply configuration, official, then supplementary source priority.

    Selecting a source here never writes its value to a candidate record. The
    returned assessment is a separate audit object with explicit provenance.
    """
    configured = _configuration_values(configuration).get(field_name)
    if _present(configured):
        return FieldCompleteness(
            field_name,
            configured,
            MetadataSource.CONFIGURATION,
            f"config/elections.json#{configuration.election_id}",
        )

    official = _official_consensus(field_name, records)
    if official.complete:
        return official

    supplementary = supplementary_metadata.get(field_name)
    if supplementary is not None and _present(supplementary.value):
        return FieldCompleteness(
            field_name,
            supplementary.value,
            MetadataSource.SUPPLEMENTARY,
            supplementary.source_reference,
        )
    return official


def assess_layered_completeness(
    configuration: ElectionConfiguration,
    records: Sequence[CandidateResultRecord],
    *,
    supplementary_metadata: Mapping[str, SupplementaryMetadataValue] | None = None,
) -> LayeredCompletenessReport:
    """Assess the three project data layers without mutating extraction output."""
    supplementary = supplementary_metadata or {}
    election_fields = tuple(
        _election_field(field_name, configuration, records, supplementary)
        for field_name in ELECTION_FIELDS
    )
    election_status, election_missing = _status(election_fields)
    election = ElectionCompleteness(
        election_id=configuration.election_id,
        status=election_status,
        fields=election_fields,
        missing_fields=election_missing,
    )

    by_source_url: dict[str, list[CandidateResultRecord]] = defaultdict(list)
    for record in records:
        by_source_url[record.source_url].append(record)

    divisions = []
    for source_url, division_records in sorted(by_source_url.items()):
        fields = tuple(
            _official_consensus(attribute_name, division_records)
            for _, attribute_name in DIVISION_FIELDS
        )
        # Report names match the existing data model, while the first field
        # also supplies the human-readable division label.
        division_status, division_missing = _status(fields)
        division_name = fields[0].value if isinstance(fields[0].value, str) else None
        divisions.append(
            DivisionCompleteness(
                division_ward_name=division_name,
                source_url=source_url,
                status=division_status,
                fields=fields,
                missing_fields=division_missing,
            )
        )

    candidates = []
    for record in records:
        fields = tuple(
            FieldCompleteness(
                report_name,
                getattr(record, attribute_name),
                MetadataSource.OFFICIAL if _present(getattr(record, attribute_name)) else MetadataSource.MISSING,
                record.source_url if _present(getattr(record, attribute_name)) else None,
                "Published as Outcome on the official candidate table."
                if report_name == "elected_status" and _present(record.outcome)
                else None,
            )
            for report_name, attribute_name in CANDIDATE_FIELDS
        )
        candidate_status, candidate_missing = _status(fields)
        candidates.append(
            CandidateCompleteness(
                candidate_name=record.candidate_name,
                source_url=record.source_url,
                status=candidate_status,
                fields=fields,
                missing_fields=candidate_missing,
            )
        )

    return LayeredCompletenessReport(
        election=election,
        divisions=tuple(divisions),
        candidates=tuple(candidates),
    )
