"""Candidate-level result extraction from indexed search evidence."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

from election_extractor.models import DiscoveredElectionArea, SearchResult
from election_extractor.search_providers.base import SearchProvider
from election_extractor.url_utils import normalise_area_result_url


class ExtractionStatus(str, Enum):
    """Describe the evidence available for an area or candidate record."""

    # COMPLETE and INCOMPLETE apply to candidate records. NO_EVIDENCE and
    # SEARCH_FAILED describe an area attempt where no candidate row is created.
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    NO_EVIDENCE = "no_evidence"
    SEARCH_FAILED = "search_failed"


@dataclass(frozen=True)
class CandidateResultRecord:
    """Store one published candidate result without filling unsupported values."""

    election_name: str | None
    election_date: str | None
    authority: str | None
    division_ward_name: str | None
    number_of_seats: int | None
    candidate_name: str
    original_party_name: str | None
    votes_received: int | None
    vote_share: float | None
    outcome: str | None
    electorate: int | None
    ballot_papers_issued: int | None
    ballot_papers_rejected: int | None
    turnout: float | None
    source_url: str
    extraction_status: ExtractionStatus
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionAttempt:
    """Record the indexed search performed for one discovered result URL."""

    source_url: str
    query: str
    status: ExtractionStatus
    result_count: int
    candidate_record_count: int
    error: str | None = None


@dataclass(frozen=True)
class ExtractionReport:
    """Return candidate records together with area-level extraction attempts."""

    records: tuple[CandidateResultRecord, ...]
    attempts: tuple[ExtractionAttempt, ...]


# Indexed snippets can publish the same field under several visible labels.
# Every accepted label maps to one stable output field without changing values.
FIELD_ALIASES = {
    "election name": "election_name",
    "election date": "election_date",
    "authority": "authority",
    "division ward": "division_ward_name",
    "division": "division_ward_name",
    "ward": "division_ward_name",
    "number of seats": "number_of_seats",
    "seats": "number_of_seats",
    "candidate name": "candidate_name",
    "candidate": "candidate_name",
    "original party name": "original_party_name",
    "party name": "original_party_name",
    "party": "original_party_name",
    "votes received": "votes_received",
    "votes": "votes_received",
    "vote share": "vote_share",
    "outcome": "outcome",
    "electorate": "electorate",
    "ballot papers issued": "ballot_papers_issued",
    "ballot papers rejected": "ballot_papers_rejected",
    "rejected ballots": "ballot_papers_rejected",
    "turnout": "turnout",
}

# This list is the single completeness rule for candidate records. A field that
# remains None is both listed in missing_fields and reflected in the status.
REQUIRED_RECORD_FIELDS = (
    "election_name",
    "election_date",
    "authority",
    "division_ward_name",
    "number_of_seats",
    "candidate_name",
    "original_party_name",
    "votes_received",
    "vote_share",
    "outcome",
    "electorate",
    "ballot_papers_issued",
    "ballot_papers_rejected",
    "turnout",
)

MISSING_MARKERS = {"", "-", "n/a", "na", "not available", "unknown"}


def build_extraction_query(area: DiscoveredElectionArea) -> str:
    """Build one indexed-search query for a discovered official result URL."""
    source_url = normalise_area_result_url(area.result_url)
    # The provider searches its external index for this exact official URL; this
    # function never opens or scrapes the council page itself.
    return (
        f'site:mycouncil.surreycc.gov.uk "{source_url}" '
        '"Election candidate" "Votes"'
    )


def _normalise_label(label: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", label.casefold()).split())


def _parse_indexed_fields(result: SearchResult) -> dict[str, str]:
    """Read explicit label-value pairs from an indexed title and snippet."""
    combined = " | ".join(part for part in (result.title, result.snippet) if part)
    fields: dict[str, str] = {}
    # Only explicit "label: value" segments are accepted. Free prose is ignored
    # because treating it as structured data could invent a value or candidate.
    for segment in re.split(r"\s*(?:\||;|\n)\s*", combined):
        if ":" not in segment:
            continue
        label, value = segment.split(":", 1)
        field_name = FIELD_ALIASES.get(_normalise_label(label))
        cleaned_value = " ".join(value.split())
        if field_name and cleaned_value.casefold() not in MISSING_MARKERS:
            fields[field_name] = cleaned_value
    return fields


def _matching_evidence(
    area: DiscoveredElectionArea,
    results: Iterable[SearchResult],
) -> tuple[dict[str, str], ...]:
    """Keep only indexed evidence that points to the requested official area URL."""
    source_url = normalise_area_result_url(area.result_url)
    evidence = []
    for result in results:
        try:
            result_url = normalise_area_result_url(result.url)
        except ValueError:
            continue
        # A result for another official ward is still unrelated evidence and
        # must not be mixed into the requested area.
        if result_url != source_url:
            continue
        fields = _parse_indexed_fields(result)
        if fields:
            evidence.append(fields)
    return tuple(evidence)


def _text_consensus(values: Iterable[str | None]) -> str | None:
    """Return one supported value, or None when evidence is missing or conflicts."""
    cleaned = [" ".join(value.split()) for value in values if value]
    # Case differences do not create a conflict, but genuinely different values
    # remain unresolved instead of selecting the first search result.
    distinct = {value.casefold(): value for value in cleaned}
    if len(distinct) != 1:
        return None
    return next(iter(distinct.values()))


def _parse_integer(value: str | None) -> int | None:
    """Parse a published whole number without replacing invalid text with zero."""
    if value is None:
        return None
    cleaned = value.replace(",", "").replace(" ", "")
    return int(cleaned) if re.fullmatch(r"\d+", cleaned) else None


def _parse_percentage(value: str | None) -> float | None:
    """Parse a published percentage while preserving absence as None."""
    if value is None:
        return None
    cleaned = value.strip().removesuffix("%").strip()
    return float(cleaned) if re.fullmatch(r"\d+(?:\.\d+)?", cleaned) else None


def _area_value(
    area_value: str | None,
    evidence: Sequence[dict[str, str]],
    field_name: str,
) -> str | None:
    # Discovery metadata is valid input evidence. Conflicts with indexed fields
    # remain unresolved instead of selecting one value arbitrarily.
    values = [area_value]
    values.extend(item.get(field_name) for item in evidence)
    return _text_consensus(values)


def _candidate_groups(
    evidence: Sequence[dict[str, str]],
) -> dict[tuple[str, str], list[dict[str, str]]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for item in evidence:
        candidate = item.get("candidate_name")
        if not candidate:
            # Metadata-only search results must not create invented candidate rows.
            continue
        party = item.get("original_party_name", "")
        # Candidate and original party together prevent two genuinely different
        # candidacies with the same name from being merged accidentally.
        key = (candidate.casefold(), party.casefold())
        groups.setdefault(key, []).append(item)
    return groups


def _missing_fields(values: dict[str, object]) -> tuple[str, ...]:
    return tuple(name for name in REQUIRED_RECORD_FIELDS if values.get(name) is None)


def _records_for_area(
    area: DiscoveredElectionArea,
    evidence: Sequence[dict[str, str]],
) -> tuple[CandidateResultRecord, ...]:
    source_url = normalise_area_result_url(area.result_url)
    # Election-level values are shared by every candidate in this area. They are
    # resolved once, using agreement across all matching indexed evidence.
    area_fields = {
        "election_name": _area_value(area.election_name, evidence, "election_name"),
        "election_date": _text_consensus(item.get("election_date") for item in evidence),
        "authority": _text_consensus(item.get("authority") for item in evidence),
        "division_ward_name": _area_value(
            area.division_ward_name,
            evidence,
            "division_ward_name",
        ),
        "number_of_seats": _parse_integer(
            _text_consensus(item.get("number_of_seats") for item in evidence)
        ),
        "electorate": _parse_integer(
            _text_consensus(item.get("electorate") for item in evidence)
        ),
        "ballot_papers_issued": _parse_integer(
            _text_consensus(item.get("ballot_papers_issued") for item in evidence)
        ),
        "ballot_papers_rejected": _parse_integer(
            _text_consensus(item.get("ballot_papers_rejected") for item in evidence)
        ),
        "turnout": _parse_percentage(
            _text_consensus(item.get("turnout") for item in evidence)
        ),
    }

    records = []
    candidate_groups = _candidate_groups(evidence)
    for group_key in sorted(candidate_groups):
        items = candidate_groups[group_key]
        # Candidate-level values are resolved only within that candidate's
        # evidence group, so votes and outcomes cannot leak between candidates.
        values: dict[str, object] = {
            **area_fields,
            "candidate_name": _text_consensus(item.get("candidate_name") for item in items),
            "original_party_name": _text_consensus(
                item.get("original_party_name") for item in items
            ),
            "votes_received": _parse_integer(
                _text_consensus(item.get("votes_received") for item in items)
            ),
            "vote_share": _parse_percentage(
                _text_consensus(item.get("vote_share") for item in items)
            ),
            "outcome": _text_consensus(item.get("outcome") for item in items),
        }
        missing = _missing_fields(values)
        # Missing evidence changes the status but never blocks preservation of
        # the published fields that were actually available.
        status = ExtractionStatus.INCOMPLETE if missing else ExtractionStatus.COMPLETE
        records.append(
            CandidateResultRecord(
                election_name=values["election_name"],
                election_date=values["election_date"],
                authority=values["authority"],
                division_ward_name=values["division_ward_name"],
                number_of_seats=values["number_of_seats"],
                candidate_name=str(values["candidate_name"]),
                original_party_name=values["original_party_name"],
                votes_received=values["votes_received"],
                vote_share=values["vote_share"],
                outcome=values["outcome"],
                electorate=values["electorate"],
                ballot_papers_issued=values["ballot_papers_issued"],
                ballot_papers_rejected=values["ballot_papers_rejected"],
                turnout=values["turnout"],
                source_url=source_url,
                extraction_status=status,
                missing_fields=missing,
            )
        )
    return tuple(records)


def extract_candidate_results(
    areas: Sequence[DiscoveredElectionArea],
    provider: SearchProvider,
) -> ExtractionReport:
    """Extract candidate records for discovered areas using indexed evidence only."""
    records: list[CandidateResultRecord] = []
    attempts: list[ExtractionAttempt] = []

    # Sort by canonical URL so output does not depend on discovery input order.
    ordered_areas = sorted(areas, key=lambda area: normalise_area_result_url(area.result_url))
    for area in ordered_areas:
        source_url = normalise_area_result_url(area.result_url)
        query = build_extraction_query(area)
        try:
            # SearchProvider is the only external access point. Tests replace it
            # with MockSearchProvider, so no network or council request occurs.
            search_results = tuple(provider.search(query))
        except Exception as exc:
            attempts.append(
                ExtractionAttempt(
                    source_url=source_url,
                    query=query,
                    status=ExtractionStatus.SEARCH_FAILED,
                    result_count=0,
                    candidate_record_count=0,
                    error=type(exc).__name__,
                )
            )
            continue

        evidence = _matching_evidence(area, search_results)
        area_records = _records_for_area(area, evidence)
        # NO_EVIDENCE creates no placeholder candidate. INCOMPLETE means at least
        # one real candidate was found but one or more required fields were absent.
        if not evidence or not area_records:
            attempt_status = ExtractionStatus.NO_EVIDENCE
        elif any(
            record.extraction_status is ExtractionStatus.INCOMPLETE
            for record in area_records
        ):
            attempt_status = ExtractionStatus.INCOMPLETE
        else:
            attempt_status = ExtractionStatus.COMPLETE

        records.extend(area_records)
        attempts.append(
            ExtractionAttempt(
                source_url=source_url,
                query=query,
                status=attempt_status,
                result_count=len(search_results),
                candidate_record_count=len(area_records),
            )
        )

    return ExtractionReport(tuple(records), tuple(attempts))
