"""Candidate-level result extraction from indexed search evidence."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import parse_qsl, urlsplit

from election_extractor.models import DiscoveredElectionArea, SearchResult
from election_extractor.official_source import (
    OfficialPageClassification,
    OfficialPageClient,
    OfficialPageDiagnostic,
    fetch_and_diagnose_official_page,
    parse_official_election_page,
)
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


class EvidenceSourceType(str, Enum):
    """Identify the evidence tier used for an extracted value or record."""

    OFFICIAL = "official"
    INDEXED_SEARCH = "indexed_search"
    ARCHIVE = "archive"


@dataclass(frozen=True)
class FieldEvidence:
    """Trace one extracted field back to indexed search evidence."""

    field_name: str
    published_value: str
    source_url: str
    search_query: str
    search_result_title: str
    search_result_snippet: str
    evidence_source: str = "SerpAPI indexed search"
    source_type: EvidenceSourceType = EvidenceSourceType.INDEXED_SEARCH
    extraction_timestamp: str | None = None


@dataclass(frozen=True)
class EvidenceConflict:
    """Preserve every conflicting published value instead of selecting one."""

    field_name: str
    published_values: tuple[str, ...]
    evidence: tuple[FieldEvidence, ...]


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
    field_evidence: tuple[FieldEvidence, ...] = ()
    conflicts: tuple[EvidenceConflict, ...] = ()
    source_type: EvidenceSourceType = EvidenceSourceType.INDEXED_SEARCH
    extraction_timestamp: str | None = None
    election_type: str | None = None
    final_position: int | None = None
    elected: str | None = None
    winning_candidate: str | None = None
    winning_party: str | None = None
    winning_margin: int | None = None
    total_votes: int | None = None
    valid_votes: int | None = None


@dataclass(frozen=True)
class ExtractionAttempt:
    """Record the indexed search performed for one discovered result URL."""

    source_url: str
    query: str
    status: ExtractionStatus
    result_count: int
    candidate_record_count: int
    error: str | None = None
    election_name: str | None = None
    division_ward_name: str | None = None
    search_date: str | None = None
    domains_searched: tuple[str, ...] = ("mycouncil.surreycc.gov.uk",)
    accepted_result_count: int = 0
    excluded_result_count: int = 0
    source_type: EvidenceSourceType = EvidenceSourceType.INDEXED_SEARCH


@dataclass(frozen=True)
class ExtractionReport:
    """Return candidate records together with area-level extraction attempts."""

    records: tuple[CandidateResultRecord, ...]
    attempts: tuple[ExtractionAttempt, ...]
    official_diagnostics: tuple[OfficialPageDiagnostic, ...] = ()


@dataclass(frozen=True)
class _ParsedEvidence:
    """Keep parsed values together with the exact query and indexed snippet."""

    fields: tuple[tuple[str, str], ...]
    source_url: str
    search_query: str
    search_result_title: str
    search_result_snippet: str
    truncated: bool
    source_type: EvidenceSourceType = EvidenceSourceType.INDEXED_SEARCH
    extraction_timestamp: str | None = None

    def as_dict(self) -> dict[str, str]:
        return dict(self.fields)


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
    "election type": "election_type",
    "final position": "final_position",
    "position": "final_position",
    "elected": "elected",
    "winning candidate": "winning_candidate",
    "winning party": "winning_party",
    "winning margin": "winning_margin",
    "total votes": "total_votes",
    "valid votes": "valid_votes",
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
DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?:19|20)\d{2})\b",
    re.IGNORECASE,
)
PARTY_NAMES = (
    "Residents Associations of Epsom and Ewell",
    "Residents for Guildford and Villages",
    "Labour and Co-operative",
    "UK Independence Party",
    "Guildford Greenbelt Group",
    "Liberal Democrats",
    "The Green Party",
    "Conservative",
    "Green Party",
    "Reform UK",
    "Independent",
    "Labour",
    "UKIP",
)
PARTY_TEXT_PATTERN = "|".join(re.escape(name) for name in PARTY_NAMES)
OUTCOME_PATTERN = r"Not elected|Elected"


def build_extraction_query(area: DiscoveredElectionArea) -> str:
    """Return the original exact-URL query for backward compatibility."""
    return build_extraction_queries(area)[0]


def build_extraction_queries(area: DiscoveredElectionArea) -> tuple[str, ...]:
    """Build several evidence queries for one confirmed ward or division."""
    source_url = normalise_area_result_url(area.result_url)
    ward = area.division_ward_name or ""
    year = str(area.election_year) if area.election_year is not None else ""
    queries = [
        f'site:mycouncil.surreycc.gov.uk "{source_url}" '
        '"Election candidate" "Votes"',
        (
            f'"{ward}" "Surrey County Council" '
            f'"Election Results" "{year}"'
        ),
        f'"{ward}" candidates votes "{year}"',
        (
            "site:mycouncil.surreycc.gov.uk "
            f'"{ward}" election results "{year}"'
        ),
        (
            f'"{ward}" councillor "Surrey County Council" '
            f'"{year}"'
        ),
        (
            f'"{ward}" Conservative Labour "Liberal Democrats" '
            f'"{year}"'
        ),
    ]
    # Empty metadata must not produce broad, unsupported searches.
    return tuple(
        dict.fromkeys(
            query for query in queries if ward or query == queries[0]
        )
    )


def _normalise_label(label: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", label.casefold()).split())


def _parse_indexed_fields(result: SearchResult) -> dict[str, str]:
    """Read the original explicit label-value format without changing values."""
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


def _published_metadata(result: SearchResult) -> dict[str, str]:
    """Extract only election metadata explicitly visible in title or snippet."""
    text = " ".join(part for part in (result.title, result.snippet) if part)
    metadata: dict[str, str] = {}
    date_match = DATE_PATTERN.search(text)
    if date_match:
        metadata["election_date"] = date_match.group(1)
    election_match = re.search(
        r"(County Council\s+(?:By-)?Election\s+(?:19|20)\d{2})",
        text,
        re.IGNORECASE,
    )
    if election_match:
        metadata["election_name"] = " ".join(election_match.group(1).split())
    if "surrey county council" in text.casefold():
        metadata["authority"] = "Surrey County Council"
    area_match = re.search(
        r"^Election results for\s+(.+?)(?:,\s*\d{1,2}\s+\w+\s+\d{4}|\s*[-|–—])",
        " ".join(result.title.split()),
        re.IGNORECASE,
    )
    if not area_match:
        area_match = re.search(
            r"^(.+?)\s*[-|–—]\s*results\b",
            " ".join(result.title.split()),
            re.IGNORECASE,
        )
    if area_match:
        metadata["division_ward_name"] = area_match.group(1).strip(" ,-|–—")
    return metadata


def _looks_like_candidate_name(value: str) -> bool:
    """Require a plausible published personal name before creating a record."""
    cleaned = " ".join(value.split()).strip(" ,.-")
    words = cleaned.split()
    if not 2 <= len(words) <= 10:
        return False
    forbidden = {
        "candidate",
        "party",
        "votes",
        "outcome",
        "election",
        "results",
        "council",
        "county",
        "thursday",
    }
    if any(word.casefold().strip(".,") in forbidden for word in words):
        return False
    return all(re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ'’.-]+", word) for word in words)


def _clean_published_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip(" ,.")
    if not cleaned or cleaned.casefold() in MISSING_MARKERS or "..." in value:
        return None
    return cleaned


def _parse_comma_candidate_rows(snippet: str) -> list[dict[str, str]]:
    """Parse ModernGov's comma-separated candidate rows conservatively."""
    rows = []
    segments = re.split(r"\s*(?:;|·|\n|(?<=\.)\s+(?=[A-Z]))\s*", snippet)
    for segment in segments:
        if "," not in segment:
            continue
        parts = [part.strip() for part in segment.strip().strip(".").split(",")]
        if any(part.casefold() in {"candidate", "election candidate"} for part in parts[:1]):
            continue
        vote_index = next(
            (
                index
                for index, part in enumerate(parts)
                if re.fullmatch(r"\d[\d,]*", part.replace(" ", ""))
            ),
            None,
        )
        if vote_index is not None and vote_index >= 1:
            if vote_index == 1:
                candidate = parts[0]
                party = None
            else:
                candidate = ", ".join(parts[: vote_index - 1])
                party = _clean_published_value(parts[vote_index - 1])
            if not _looks_like_candidate_name(candidate):
                continue
            row = {
                "candidate_name": " ".join(candidate.split()),
                "votes_received": parts[vote_index].replace(" ", ""),
            }
            if party:
                row["original_party_name"] = party
            for part in parts[vote_index + 1 :]:
                cleaned = _clean_published_value(part)
                if not cleaned:
                    continue
                if re.fullmatch(r"\d+(?:\.\d+)?%", cleaned):
                    row["vote_share"] = cleaned
                elif cleaned.casefold() in {"elected", "not elected"}:
                    row["outcome"] = cleaned
            rows.append(row)
            continue

        # A truncated tail can still support the candidate identity, but its
        # unfinished party text must not be stored as a published party value.
        if "..." in segment and parts and _looks_like_candidate_name(parts[0]):
            rows.append({"candidate_name": " ".join(parts[0].split())})
    return rows


def _parse_pipe_candidate_rows(snippet: str) -> list[dict[str, str]]:
    """Parse a visible Candidate | Party | Votes table when headers are present."""
    cells = [" ".join(cell.split()) for cell in snippet.replace("\n", "|").split("|")]
    cells = [cell for cell in cells if cell]
    normalised = [_normalise_label(cell) for cell in cells]
    header_index = next(
        (
            index
            for index in range(max(len(cells) - 2, 0))
            if normalised[index] in {"candidate", "election candidate"}
            and normalised[index + 1] == "party"
            and normalised[index + 2] == "votes"
        ),
        None,
    )
    if header_index is None:
        return []
    headers = ["candidate", "party", "votes"]
    next_index = header_index + 3
    while next_index < len(cells) and len(headers) < 5:
        header = normalised[next_index]
        if header == "" and cells[next_index].strip() == "%":
            header = "vote share"
        if header not in {"vote share", "outcome"}:
            break
        headers.append(header)
        next_index += 1
    data = cells[header_index + len(headers) :]
    rows = []
    for offset in range(0, len(data), len(headers)):
        values = data[offset : offset + len(headers)]
        if not values or not _looks_like_candidate_name(values[0]):
            continue
        row: dict[str, str] = {"candidate_name": values[0]}
        for header, value in zip(headers[1:], values[1:]):
            cleaned = _clean_published_value(value)
            if not cleaned:
                continue
            if header == "party":
                row["original_party_name"] = cleaned
            elif header == "votes":
                row["votes_received"] = cleaned
            elif header == "vote share" or value.endswith("%"):
                row["vote_share"] = cleaned
            elif header == "outcome":
                row["outcome"] = cleaned
        rows.append(row)
    return rows


def _parse_text_candidate_rows(snippet: str) -> list[dict[str, str]]:
    """Parse undelimited text only when a published party phrase is explicit."""
    pattern = re.compile(
        rf"(?P<candidate>[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+"
        rf"(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+){{1,9}})\s+"
        rf"(?P<party>{PARTY_TEXT_PATTERN})\s+"
        rf"(?P<votes>\d[\d,]*)"
        rf"(?:\s+(?P<share>\d+(?:\.\d+)?%))?"
        rf"(?:\s+(?P<outcome>{OUTCOME_PATTERN}))?"
    )
    rows = []
    for match in pattern.finditer(snippet):
        candidate = " ".join(match.group("candidate").split())
        if not _looks_like_candidate_name(candidate):
            continue
        row = {
            "candidate_name": candidate,
            "original_party_name": match.group("party"),
            "votes_received": match.group("votes"),
        }
        if match.group("share"):
            row["vote_share"] = match.group("share")
        if match.group("outcome"):
            row["outcome"] = match.group("outcome")
        rows.append(row)
    return rows


def _parsed_rows(result: SearchResult) -> tuple[dict[str, str], ...]:
    """Combine supported real and mocked formats without inventing fields."""
    metadata = _published_metadata(result)
    labelled = _parse_indexed_fields(result)
    candidate_rows: list[dict[str, str]] = []
    if labelled.get("candidate_name"):
        candidate_rows.append(labelled)
    candidate_rows.extend(_parse_pipe_candidate_rows(result.snippet))
    candidate_rows.extend(_parse_comma_candidate_rows(result.snippet))
    candidate_rows.extend(_parse_text_candidate_rows(result.snippet))

    if not candidate_rows:
        combined_metadata = {**metadata, **labelled}
        return (combined_metadata,) if combined_metadata else ()

    output = []
    seen = set()
    for row in candidate_rows:
        values = {**metadata, **labelled, **row}
        item = tuple(sorted(values.items()))
        if item not in seen:
            seen.add(item)
            output.append(values)
    return tuple(output)


def _result_area_id(url: str) -> str:
    normalised = normalise_area_result_url(url)
    values = [
        value
        for name, value in parse_qsl(urlsplit(normalised).query, keep_blank_values=True)
        if name == "ID"
    ]
    if len(values) != 1:
        raise ValueError("Result URL does not contain one ID value.")
    return values[0]


def _matching_evidence(
    area: DiscoveredElectionArea,
    query: str,
    results: Iterable[SearchResult],
) -> tuple[_ParsedEvidence, ...]:
    """Keep only indexed evidence that points to the requested official area URL."""
    source_url = normalise_area_result_url(area.result_url)
    source_id = _result_area_id(source_url)
    evidence = []
    extraction_timestamp = datetime.now(timezone.utc).isoformat()
    for result in results:
        try:
            result_url = normalise_area_result_url(result.url)
        except ValueError:
            continue
        # A result for another official ward is still unrelated evidence and
        # must not be mixed into the requested area.
        if _result_area_id(result_url) != source_id:
            continue
        for fields in _parsed_rows(result):
            if fields:
                evidence.append(
                    _ParsedEvidence(
                        fields=tuple(sorted(fields.items())),
                        source_url=result_url,
                        search_query=query,
                        search_result_title=result.title,
                        search_result_snippet=result.snippet,
                        truncated="..." in result.snippet or "…" in result.snippet,
                        source_type=EvidenceSourceType.INDEXED_SEARCH,
                        extraction_timestamp=extraction_timestamp,
                    )
                )
    return tuple(evidence)


def _official_evidence(
    area: DiscoveredElectionArea,
    body: str,
    final_url: str,
) -> tuple[_ParsedEvidence, ...]:
    """Convert exact official table cells into the existing evidence pipeline."""
    page_data = parse_official_election_page(body)
    shared_fields = dict(page_data.shared_fields)
    shared_evidence = dict(page_data.shared_evidence)
    timestamp = datetime.now(timezone.utc).isoformat()
    output = []
    for candidate in page_data.candidate_rows:
        fields = {**shared_fields, **dict(candidate.fields)}
        evidence_text = " | ".join(
            dict.fromkeys(
                (*shared_evidence.values(), candidate.evidence_text)
            )
        )
        output.append(
            _ParsedEvidence(
                fields=tuple(sorted(fields.items())),
                source_url=final_url,
                search_query="",
                search_result_title=f"Official Surrey result page: {area.division_ward_name or ''}".strip(),
                search_result_snippet=evidence_text,
                truncated=False,
                source_type=EvidenceSourceType.OFFICIAL,
                extraction_timestamp=timestamp,
            )
        )
    return tuple(output)


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


def _candidate_groups(
    evidence: Sequence[_ParsedEvidence],
) -> dict[str, list[_ParsedEvidence]]:
    groups: dict[str, list[_ParsedEvidence]] = {}
    for item in evidence:
        candidate = item.as_dict().get("candidate_name")
        if not candidate:
            # Metadata-only search results must not create invented candidate rows.
            continue
        # The candidate identity is the grouping key. Conflicting party or vote
        # values then remain attached to one candidate as explicit conflicts.
        key = " ".join(candidate.split()).casefold()
        groups.setdefault(key, []).append(item)
    return groups


def _field_evidence(
    evidence: Sequence[_ParsedEvidence],
    field_name: str,
) -> tuple[FieldEvidence, ...]:
    output = []
    seen = set()
    for item in evidence:
        value = item.as_dict().get(field_name)
        if not value:
            continue
        field_evidence = FieldEvidence(
            field_name=field_name,
            published_value=value,
            source_url=item.source_url,
            search_query=item.search_query,
            search_result_title=item.search_result_title,
            search_result_snippet=item.search_result_snippet,
            evidence_source=(
                "Official Surrey page"
                if item.source_type is EvidenceSourceType.OFFICIAL
                else "SerpAPI indexed search"
            ),
            source_type=item.source_type,
            extraction_timestamp=item.extraction_timestamp,
        )
        key = (
            field_evidence.published_value.casefold(),
            field_evidence.source_url,
            field_evidence.search_query,
            field_evidence.search_result_snippet,
        )
        if key not in seen:
            seen.add(key)
            output.append(field_evidence)
    return tuple(output)


def _resolve_field(
    evidence: Sequence[_ParsedEvidence],
    field_name: str,
    *,
    discovery_value: str | None = None,
    source_url: str,
) -> tuple[str | None, tuple[FieldEvidence, ...], EvidenceConflict | None]:
    supporting = list(_field_evidence(evidence, field_name))
    if discovery_value:
        supporting.insert(
            0,
            FieldEvidence(
                field_name=field_name,
                published_value=discovery_value,
                source_url=source_url,
                search_query="Discovery metadata",
                # Discovery metadata is not a substitute for published page
                # evidence. This explicit audit text identifies the value and
                # keeps its lower-priority source visible if it conflicts.
                search_result_title="Discovery metadata",
                search_result_snippet=(
                    f"Discovery metadata {field_name}: {discovery_value}"
                ),
                evidence_source="Discovery metadata",
                source_type=EvidenceSourceType.INDEXED_SEARCH,
                extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )
    distinct: dict[str, str] = {}
    for item in supporting:
        cleaned = " ".join(item.published_value.split())
        distinct.setdefault(cleaned.casefold(), cleaned)
    if not distinct:
        return None, tuple(supporting), None
    if len(distinct) == 1:
        return next(iter(distinct.values())), tuple(supporting), None
    conflict = EvidenceConflict(
        field_name=field_name,
        published_values=tuple(distinct.values()),
        evidence=tuple(supporting),
    )
    return None, tuple(supporting), conflict


def _missing_fields(values: dict[str, object]) -> tuple[str, ...]:
    return tuple(name for name in REQUIRED_RECORD_FIELDS if values.get(name) is None)


def _records_for_area(
    area: DiscoveredElectionArea,
    evidence: Sequence[_ParsedEvidence],
) -> tuple[CandidateResultRecord, ...]:
    source_url = normalise_area_result_url(area.result_url)
    # Resolve shared fields once. Conflicts remain None and carry every source.
    area_raw: dict[str, str | None] = {}
    area_field_evidence: list[FieldEvidence] = []
    area_conflicts: list[EvidenceConflict] = []
    for field_name, discovery_value in (
        ("election_name", area.election_name),
        ("election_date", None),
        ("authority", None),
        ("division_ward_name", area.division_ward_name),
        ("number_of_seats", None),
        ("electorate", None),
        ("ballot_papers_issued", None),
        ("ballot_papers_rejected", None),
        ("turnout", None),
        ("election_type", None),
        ("winning_candidate", None),
        ("winning_party", None),
        ("winning_margin", None),
        ("total_votes", None),
        ("valid_votes", None),
    ):
        value, supporting, conflict = _resolve_field(
            evidence,
            field_name,
            discovery_value=discovery_value,
            source_url=source_url,
        )
        area_raw[field_name] = value
        area_field_evidence.extend(supporting)
        if conflict:
            area_conflicts.append(conflict)

    area_fields: dict[str, object] = {
        "election_name": area_raw["election_name"],
        "election_date": area_raw["election_date"],
        "authority": area_raw["authority"],
        "division_ward_name": area_raw["division_ward_name"],
        "number_of_seats": _parse_integer(area_raw["number_of_seats"]),
        "electorate": _parse_integer(area_raw["electorate"]),
        "ballot_papers_issued": _parse_integer(area_raw["ballot_papers_issued"]),
        "ballot_papers_rejected": _parse_integer(area_raw["ballot_papers_rejected"]),
        "turnout": _parse_percentage(area_raw["turnout"]),
        "election_type": area_raw["election_type"],
        "winning_candidate": area_raw["winning_candidate"],
        "winning_party": area_raw["winning_party"],
        "winning_margin": _parse_integer(area_raw["winning_margin"]),
        "total_votes": _parse_integer(area_raw["total_votes"]),
        "valid_votes": _parse_integer(area_raw["valid_votes"]),
    }

    records = []
    candidate_groups = _candidate_groups(evidence)
    for group_key in sorted(candidate_groups):
        items = candidate_groups[group_key]
        # Candidate-level values are resolved only within that candidate's
        # evidence group, so votes and outcomes cannot leak between candidates.
        candidate_raw: dict[str, str | None] = {}
        candidate_evidence: list[FieldEvidence] = []
        candidate_conflicts: list[EvidenceConflict] = []
        for field_name in (
            "candidate_name",
            "original_party_name",
            "votes_received",
            "vote_share",
            "outcome",
            "final_position",
            "elected",
        ):
            value, supporting, conflict = _resolve_field(
                items,
                field_name,
                source_url=source_url,
            )
            candidate_raw[field_name] = value
            candidate_evidence.extend(supporting)
            if conflict:
                candidate_conflicts.append(conflict)
        values: dict[str, object] = {
            **area_fields,
            "candidate_name": candidate_raw["candidate_name"],
            "original_party_name": candidate_raw["original_party_name"],
            "votes_received": _parse_integer(candidate_raw["votes_received"]),
            "vote_share": _parse_percentage(candidate_raw["vote_share"]),
            "outcome": candidate_raw["outcome"],
            "final_position": _parse_integer(candidate_raw["final_position"]),
            "elected": candidate_raw["elected"],
        }
        missing = _missing_fields(values)
        # Missing evidence changes the status but never blocks preservation of
        # the published fields that were actually available.
        conflicts = tuple((*area_conflicts, *candidate_conflicts))
        truncated_only = all(item.truncated for item in items)
        status = (
            ExtractionStatus.INCOMPLETE
            if missing or conflicts or truncated_only
            else ExtractionStatus.COMPLETE
        )
        candidate_name = candidate_raw["candidate_name"]
        if candidate_name is None:
            # A conflict in the identity itself cannot support a candidate row.
            continue
        source_types = {item.source_type for item in items}
        source_type = (
            next(iter(source_types))
            if len(source_types) == 1
            else EvidenceSourceType.INDEXED_SEARCH
        )
        timestamps = sorted(
            item.extraction_timestamp
            for item in items
            if item.extraction_timestamp is not None
        )
        records.append(
            CandidateResultRecord(
                election_name=values["election_name"],
                election_date=values["election_date"],
                authority=values["authority"],
                division_ward_name=values["division_ward_name"],
                number_of_seats=values["number_of_seats"],
                candidate_name=candidate_name,
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
                field_evidence=tuple((*area_field_evidence, *candidate_evidence)),
                conflicts=conflicts,
                source_type=source_type,
                extraction_timestamp=timestamps[-1] if timestamps else None,
                election_type=values["election_type"],
                final_position=values["final_position"],
                elected=values["elected"],
                winning_candidate=values["winning_candidate"],
                winning_party=values["winning_party"],
                winning_margin=values["winning_margin"],
                total_votes=values["total_votes"],
                valid_votes=values["valid_votes"],
            )
        )
    return tuple(records)


def extract_candidate_results(
    areas: Sequence[DiscoveredElectionArea],
    provider: SearchProvider,
    *,
    official_page_client: OfficialPageClient | None = None,
) -> ExtractionReport:
    """Use official pages first, then fall back to auditable indexed evidence."""
    records: list[CandidateResultRecord] = []
    attempts: list[ExtractionAttempt] = []
    diagnostics: list[OfficialPageDiagnostic] = []

    # Sort by canonical URL so output does not depend on discovery input order.
    ordered_areas = sorted(areas, key=lambda area: normalise_area_result_url(area.result_url))
    for area in ordered_areas:
        source_url = normalise_area_result_url(area.result_url)
        area_evidence: list[_ParsedEvidence] = []
        search_date = datetime.now(timezone.utc).date().isoformat()

        if official_page_client is not None:
            fetch_result = fetch_and_diagnose_official_page(
                source_url,
                official_page_client,
            )
            diagnostics.append(fetch_result.diagnostic)
            if (
                fetch_result.diagnostic.classification
                is OfficialPageClassification.VALID_ELECTION_RESULT_PAGE
                and fetch_result.body is not None
                and fetch_result.diagnostic.final_url is not None
            ):
                official_evidence = _official_evidence(
                    area,
                    fetch_result.body,
                    fetch_result.diagnostic.final_url,
                )
                official_records = _records_for_area(area, official_evidence)
                official_status = (
                    ExtractionStatus.NO_EVIDENCE
                    if not official_records
                    else ExtractionStatus.INCOMPLETE
                    if any(
                        record.extraction_status is ExtractionStatus.INCOMPLETE
                        for record in official_records
                    )
                    else ExtractionStatus.COMPLETE
                )
                attempts.append(
                    ExtractionAttempt(
                        source_url=source_url,
                        query=f"GET {source_url}",
                        status=official_status,
                        result_count=1,
                        candidate_record_count=len(official_records),
                        election_name=area.election_name,
                        division_ward_name=area.division_ward_name,
                        search_date=search_date,
                        accepted_result_count=1 if official_records else 0,
                        excluded_result_count=0 if official_records else 1,
                        source_type=EvidenceSourceType.OFFICIAL,
                    )
                )
                if official_records:
                    # A successfully parsed official page is the highest evidence
                    # tier, so lower-priority indexed snippets are not mixed in.
                    records.extend(official_records)
                    continue

        for query in build_extraction_queries(area):
            try:
                # SearchProvider remains the only external access point. Every
                # real query is retained as a separate auditable attempt.
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
                        election_name=area.election_name,
                        division_ward_name=area.division_ward_name,
                        search_date=search_date,
                        source_type=EvidenceSourceType.INDEXED_SEARCH,
                    )
                )
                continue

            query_evidence = _matching_evidence(area, query, search_results)
            query_records = _records_for_area(area, query_evidence)
            accepted_results = {
                (
                    item.source_url,
                    item.search_result_title,
                    item.search_result_snippet,
                )
                for item in query_evidence
            }
            if not query_evidence or not query_records:
                attempt_status = ExtractionStatus.NO_EVIDENCE
            elif any(
                record.extraction_status is ExtractionStatus.INCOMPLETE
                for record in query_records
            ):
                attempt_status = ExtractionStatus.INCOMPLETE
            else:
                attempt_status = ExtractionStatus.COMPLETE
            attempts.append(
                ExtractionAttempt(
                    source_url=source_url,
                    query=query,
                    status=attempt_status,
                    result_count=len(search_results),
                    candidate_record_count=len(query_records),
                    election_name=area.election_name,
                    division_ward_name=area.division_ward_name,
                    search_date=search_date,
                    accepted_result_count=len(accepted_results),
                    excluded_result_count=len(search_results) - len(accepted_results),
                    source_type=EvidenceSourceType.INDEXED_SEARCH,
                )
            )
            area_evidence.extend(query_evidence)

        # Merge evidence only after every supported query has completed. This
        # allows partial snippets to complement each other without overwriting.
        records.extend(_records_for_area(area, area_evidence))

    return ExtractionReport(tuple(records), tuple(attempts), tuple(diagnostics))
