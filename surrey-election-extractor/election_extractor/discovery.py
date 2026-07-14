"""Ward and division discovery using indexed search evidence."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit

from election_extractor.models import (
    DiscoveredElectionArea,
    DiscoveryReport,
    DiscoveryStatus,
    SearchAttempt,
    SearchResult,
)
from election_extractor.search_providers.base import SearchProvider
from election_extractor.url_utils import (
    normalise_area_result_url,
    normalise_url,
    validate_index_url,
)


YEAR_PATTERN = re.compile(r"\b((?:19|20)\d{2})\b")
DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(?:19|20)\d{2})\b",
    re.IGNORECASE,
)
ARCHIVE_PATH = "/mgElectionResults.aspx"
SEARCH_DOMAIN = "mycouncil.surreycc.gov.uk"
# Search engines use several title layouts for the same council result page.
# Only these explicit layouts are accepted so an unrelated title is not treated
# as evidence for a ward or division name.
AREA_NAME_PATTERNS = (
    re.compile(r"^Election results for\s+(.+?)(?:,\s*\d{1,2}\s+\w+\s+\d{4}|\s*[-|–—])", re.IGNORECASE),
    re.compile(r"^(.+?)\s*[-|–—]\s*Election results", re.IGNORECASE),
    re.compile(r"^(.+?)\s+election result(?:s)?(?:\s*[-|–—]|$)", re.IGNORECASE),
)


@dataclass(frozen=True)
class _Evidence:
    """Keep a normalised URL with its indexed title and snippet."""

    result_url: str
    title: str
    snippet: str


@dataclass(frozen=True)
class DiscoverySearchAttempt(SearchAttempt):
    """Extend the existing audit record with real-run search context."""

    election_name: str | None = None
    election_year: int | None = None
    division_ward_name: str | None = None
    search_date: str | None = None
    domains_searched: tuple[str, ...] = (SEARCH_DOMAIN,)
    accepted_result_count: int = 0
    excluded_result_count: int = 0


@dataclass(frozen=True)
class _ElectionContext:
    """Election metadata supported by the supplied archive and indexed page."""

    year: int | None
    name: str | None
    date: str | None


@dataclass(frozen=True)
class _SearchRun:
    """Temporarily retain results so audit counts can be added after validation."""

    query: str
    results: tuple[SearchResult, ...]
    error: str | None = None
    division_ward_name: str | None = None


def _single_numeric_value(url: str, name: str) -> str | None:
    values = [
        value
        for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True)
        if key == name
    ]
    return values[0] if len(values) == 1 and values[0].isdigit() else None


def validate_discovery_source_url(url: str) -> str:
    """Accept an official area index or the official election archive page."""
    try:
        return validate_index_url(url)
    except ValueError:
        canonical = normalise_url(url)
        parsed = urlsplit(canonical)
        if parsed.path.casefold() != ARCHIVE_PATH.casefold():
            raise ValueError("URL is not a Surrey election archive or area index URL.")
        if _single_numeric_value(canonical, "ID") is None:
            raise ValueError("Election archive URL must include one numeric ID parameter.")
        return canonical


def _election_identifier(source_url: str) -> str:
    identifier = _single_numeric_value(source_url, "EID")
    if identifier is None:
        identifier = _single_numeric_value(source_url, "ID")
    if identifier is None:
        raise ValueError("Election source URL does not contain a usable election identifier.")
    return identifier


def build_search_queries(
    index_url: str,
    election_name: str | None = None,
    election_date: str | None = None,
) -> tuple[str, ...]:
    """Build deterministic queries for an official archive or area index."""
    canonical_index = validate_discovery_source_url(index_url)
    election_identifier = _election_identifier(canonical_index)
    exact_area_index = (
        "https://mycouncil.surreycc.gov.uk/"
        f"mgElectionElectionAreaResults.aspx?EID={election_identifier}"
    )
    queries = [f'site:mycouncil.surreycc.gov.uk "{canonical_index}"']
    if canonical_index != exact_area_index:
        # ModernGov uses the same numeric election identifier on the archive
        # and area-index views. The exact official index query supplies context;
        # it does not construct or assume any ward result ID.
        queries.append(f'site:mycouncil.surreycc.gov.uk "{exact_area_index}"')
    queries.extend(
        [
        (
            "site:mycouncil.surreycc.gov.uk "
            f'inurl:mgElectionElectionAreaResults.aspx "EID={election_identifier}"'
        ),
        ]
    )
    # Real area URLs use ID rather than EID. Election name and date therefore
    # provide the relationship back to the supplied election archive.
    if election_date:
        queries.append(
            "site:mycouncil.surreycc.gov.uk "
            f'inurl:mgElectionAreaResults.aspx "{election_date}"'
        )
    if election_name:
        queries.append(
            f'site:mycouncil.surreycc.gov.uk inurl:mgElectionAreaResults.aspx "{election_name}"'
        )
    # Dictionary keys remove repeated queries while preserving creation order.
    return tuple(dict.fromkeys(queries))


def extract_area_name(title: str) -> str | None:
    """Extract an area name only when a recognised indexed-title pattern matches."""
    cleaned = " ".join(title.split())
    for pattern in AREA_NAME_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            name = match.group(1).strip(" ,-|–—")
            return name or None
    return None


def _extract_metadata(results: Iterable[SearchResult]) -> _ElectionContext:
    candidates: list[tuple[int, str, str | None]] = []
    for result in results:
        text = " ".join(part for part in (result.title, result.snippet) if part)
        year_match = YEAR_PATTERN.search(text)
        if not year_match:
            continue
        year = int(year_match.group(1))
        lower_text = text.casefold()
        if "election" not in lower_text:
            continue
        date_match = DATE_PATTERN.search(text)
        election_date = date_match.group(1) if date_match else None
        # Support both the original mocked wording and ModernGov's real wording.
        name_match = re.search(
            r"((?:19|20)\d{2}\s+Surrey County Council\s+(?:by-)?election)",
            text,
            re.IGNORECASE,
        )
        if not name_match:
            name_match = re.search(
                r"(County Council\s+(?:By-)?Election\s+(?:19|20)\d{2})",
                text,
                re.IGNORECASE,
            )
        if name_match:
            candidates.append((year, " ".join(name_match.group(1).split()), election_date))
    if not candidates:
        return _ElectionContext(None, None, None)
    year, name, election_date = sorted(
        candidates,
        key=lambda item: (item[0], item[1].casefold(), item[2] or ""),
    )[0]
    return _ElectionContext(year, name, election_date)


def _matches_election_context(result: SearchResult, context: _ElectionContext) -> bool:
    """Reject isolated result IDs that do not identify the target election."""
    if context.year is None:
        return False
    text = " ".join((result.title, result.snippet)).casefold()
    if str(context.year) not in text:
        return False
    if context.date and context.date.casefold() in text:
        return True
    if context.name and context.name.casefold() in text:
        return True
    return "county council election" in text


def _area_evidence(
    results: Iterable[SearchResult],
    context: _ElectionContext,
) -> dict[str, list[_Evidence]]:
    evidence: dict[str, list[_Evidence]] = {}
    for result in results:
        try:
            result_url = normalise_area_result_url(result.url)
        except ValueError:
            continue
        if extract_area_name(result.title) is None:
            continue
        if not _matches_election_context(result, context):
            continue
        # Group by canonical URL so duplicates from different queries or result
        # positions become one discovered election area.
        evidence.setdefault(result_url, []).append(
            _Evidence(result_url=result_url, title=result.title, snippet=result.snippet)
        )
    return evidence


def _best_area_name(items: Iterable[_Evidence]) -> str | None:
    names = {name for item in items if (name := extract_area_name(item.title))}
    if not names:
        return None
    # A deterministic choice makes output independent of search-result order.
    # The shorter recognised title fragment usually excludes publisher suffixes.
    return sorted(names, key=lambda name: (len(name), name.casefold()))[0]


def discover_election_areas(index_url: str, provider: SearchProvider) -> DiscoveryReport:
    """Discover distinct official area-result URLs and retain every search attempt."""
    canonical_index = validate_discovery_source_url(index_url)
    search_runs: list[_SearchRun] = []
    all_results: list[SearchResult] = []

    initial_queries = build_search_queries(canonical_index)
    for query in initial_queries:
        try:
            results = tuple(provider.search(query))
        except Exception as exc:
            # Keep a failed attempt in the audit and continue so another indexed
            # query can still provide partial, evidence-backed discovery.
            search_runs.append(_SearchRun(query, (), type(exc).__name__))
            continue
        search_runs.append(_SearchRun(query, results))
        all_results.extend(results)

    context = _extract_metadata(all_results)
    if context.name or context.date:
        # Context-based queries locate ID-based result pages without assuming
        # that an area URL carries the election's EID.
        context_queries = build_search_queries(
            canonical_index,
            context.name,
            context.date,
        )[len(initial_queries) :]
        for metadata_query in context_queries:
            try:
                results = tuple(provider.search(metadata_query))
            except Exception as exc:
                search_runs.append(_SearchRun(metadata_query, (), type(exc).__name__))
            else:
                search_runs.append(_SearchRun(metadata_query, results))
                all_results.extend(results)

    evidence_by_url = _area_evidence(all_results, context)
    areas = []
    for result_url in sorted(evidence_by_url):
        area_name = _best_area_name(evidence_by_url[result_url])
        # Status values make missing evidence explicit; no placeholder ward name
        # or election metadata is invented.
        if area_name is None:
            status = DiscoveryStatus.MISSING_AREA_NAME
        elif context.year is None or context.name is None:
            status = DiscoveryStatus.MISSING_ELECTION_METADATA
        else:
            status = DiscoveryStatus.DISCOVERED
        areas.append(
            DiscoveredElectionArea(
                election_year=context.year,
                election_name=context.name,
                division_ward_name=area_name,
                result_url=result_url,
                source_index_url=canonical_index,
                discovery_status=status,
            )
        )

    search_date = datetime.now(timezone.utc).date().isoformat()
    accepted_urls = set(evidence_by_url)
    attempts = []
    for run in search_runs:
        accepted = 0
        for result in run.results:
            try:
                result_url = normalise_area_result_url(result.url)
            except ValueError:
                continue
            if result_url in accepted_urls and _matches_election_context(result, context):
                accepted += 1
        attempts.append(
            DiscoverySearchAttempt(
                query=run.query,
                source_index_url=canonical_index,
                status="failed" if run.error else "completed",
                result_count=len(run.results),
                error=run.error,
                election_name=context.name,
                election_year=context.year,
                division_ward_name=run.division_ward_name,
                search_date=search_date,
                accepted_result_count=accepted,
                excluded_result_count=len(run.results) - accepted,
            )
        )

    return DiscoveryReport(canonical_index, tuple(areas), tuple(attempts))
