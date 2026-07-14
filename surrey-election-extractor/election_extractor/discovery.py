"""Ward and division discovery using indexed search evidence."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

from election_extractor.models import (
    DiscoveredElectionArea,
    DiscoveryReport,
    DiscoveryStatus,
    SearchAttempt,
    SearchResult,
)
from election_extractor.search_providers.base import SearchProvider
from election_extractor.url_utils import normalise_area_result_url, validate_index_url


YEAR_PATTERN = re.compile(r"\b((?:19|20)\d{2})\b")
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


def build_search_queries(index_url: str, election_name: str | None = None) -> tuple[str, ...]:
    """Build deterministic discovery queries from a validated index URL."""
    canonical_index = validate_index_url(index_url)
    eid = dict(parse_qsl(urlsplit(canonical_index).query))["EID"]
    queries = [
        f'site:mycouncil.surreycc.gov.uk "{canonical_index}"',
        f'site:mycouncil.surreycc.gov.uk inurl:mgElectionAreaResults.aspx "EID={eid}"',
    ]
    # Once indexed evidence supplies the election name, use it to find result
    # pages whose URLs do not contain the election EID.
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


def _extract_metadata(results: Iterable[SearchResult]) -> tuple[int | None, str | None]:
    candidates = []
    for result in results:
        text = " ".join(part for part in (result.title, result.snippet) if part)
        year_match = YEAR_PATTERN.search(text)
        if not year_match:
            continue
        year = int(year_match.group(1))
        title = " ".join(result.title.split())
        lower_title = title.casefold()
        if "surrey county council" not in lower_title or "election" not in lower_title:
            continue
        # Require the complete election phrase instead of constructing a name
        # from the year alone. Missing metadata must remain missing.
        name_match = re.search(
            r"((?:19|20)\d{2}\s+Surrey County Council\s+(?:by-)?election)",
            title,
            re.IGNORECASE,
        )
        if name_match:
            candidates.append((year, name_match.group(1)))
    if not candidates:
        return None, None
    year, name = sorted(candidates, key=lambda item: (item[0], item[1].casefold()))[0]
    return year, name


def _area_evidence(results: Iterable[SearchResult]) -> dict[str, list[_Evidence]]:
    evidence: dict[str, list[_Evidence]] = {}
    for result in results:
        try:
            result_url = normalise_area_result_url(result.url)
        except ValueError:
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
    canonical_index = validate_index_url(index_url)
    attempts: list[SearchAttempt] = []
    all_results: list[SearchResult] = []

    initial_queries = build_search_queries(canonical_index)
    for query in initial_queries:
        try:
            results = tuple(provider.search(query))
        except Exception as exc:
            # Keep a failed attempt in the audit and continue so another indexed
            # query can still provide partial, evidence-backed discovery.
            attempts.append(
                SearchAttempt(query, canonical_index, "failed", 0, type(exc).__name__)
            )
            continue
        attempts.append(SearchAttempt(query, canonical_index, "completed", len(results)))
        all_results.extend(results)

    election_year, election_name = _extract_metadata(all_results)
    if election_name:
        # The metadata-based query is a second pass, not a direct council-site
        # request. It can expose area pages omitted from the EID-based search.
        metadata_query = build_search_queries(canonical_index, election_name)[-1]
        if metadata_query not in initial_queries:
            try:
                results = tuple(provider.search(metadata_query))
            except Exception as exc:
                attempts.append(
                    SearchAttempt(metadata_query, canonical_index, "failed", 0, type(exc).__name__)
                )
            else:
                attempts.append(
                    SearchAttempt(metadata_query, canonical_index, "completed", len(results))
                )
                all_results.extend(results)

    evidence_by_url = _area_evidence(all_results)
    areas = []
    for result_url in sorted(evidence_by_url):
        area_name = _best_area_name(evidence_by_url[result_url])
        # Status values make missing evidence explicit; no placeholder ward name
        # or election metadata is invented.
        if area_name is None:
            status = DiscoveryStatus.MISSING_AREA_NAME
        elif election_year is None or election_name is None:
            status = DiscoveryStatus.MISSING_ELECTION_METADATA
        else:
            status = DiscoveryStatus.DISCOVERED
        areas.append(
            DiscoveredElectionArea(
                election_year=election_year,
                election_name=election_name,
                division_ward_name=area_name,
                result_url=result_url,
                source_index_url=canonical_index,
                discovery_status=status,
            )
        )

    return DiscoveryReport(canonical_index, tuple(areas), tuple(attempts))
