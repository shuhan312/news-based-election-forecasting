"""Official-archive-first discovery of Surrey election areas.

The normal workflow follows links published by Surrey's election archive and
area index. Indexed search remains an audited fallback when that official path
is unavailable or produces no valid area-result links.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from election_extractor.models import (
    AreaNameStatus,
    DiscoveredElectionArea,
    DiscoveryReport,
    DiscoveryStatus,
    MetadataStatus,
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
INDEX_PATH = "/mgElectionElectionAreaResults.aspx"
SEARCH_DOMAIN = "mycouncil.surreycc.gov.uk"
MAP_INDEX_HOST = "www10.surreycc.gov.uk"
# The 2026 election has two published map indexes rather than the historical
# ``mycouncil`` archive/index structure.  This explicit allow-list prevents a
# URL for another Surrey map or an arbitrary www10 page becoming a data source.
MAP_INDEX_PATHS = {
    "/electionmap/eastsurrey/": "/electionmap/eastSurrey/",
    "/electionmap/westsurrey/": "/electionmap/WestSurrey/",
}
GENERIC_AREA_LINK_TEXT = {
    "election results",
    "results",
    "view results",
    "view election results",
}

# Search engines use several title layouts for the same council result page.
# Only these explicit layouts are accepted so an unrelated title is not treated
# as evidence for a ward or division name.
AREA_NAME_PATTERNS = (
    re.compile(
        r"^Election results for\s+(.+?)(?:,\s*\d{1,2}\s+\w+\s+\d{4}|\s*[-|–—])",
        re.IGNORECASE,
    ),
    re.compile(r"^(.+?)\s*[-|–—]\s*Election results", re.IGNORECASE),
    re.compile(r"^(.+?)\s+election result(?:s)?(?:\s*[-|–—]|$)", re.IGNORECASE),
)


@dataclass(frozen=True)
class OfficialArchiveResponse:
    """Represent one ordinary public HTTP response from an archive page."""

    status_code: int
    final_url: str
    body: str


class OfficialArchiveClient(Protocol):
    """Allow real HTTP access and deterministic archive fixtures to share a contract."""

    def fetch(self, url: str) -> OfficialArchiveResponse:
        """Fetch one official archive or area-index URL without browser automation."""


class UrllibOfficialArchiveClient:
    """Use normal public HTTP only; this client does not bypass site protections."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self._timeout = timeout

    def fetch(self, url: str) -> OfficialArchiveResponse:
        canonical_url = validate_discovery_source_url(url)
        request = Request(
            canonical_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "SurreyElectionExtractor/1.0 (academic data audit)",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                body = response.read().decode(
                    response.headers.get_content_charset() or "utf-8",
                    errors="replace",
                )
                return OfficialArchiveResponse(
                    status_code=response.getcode(),
                    final_url=response.geturl(),
                    body=body,
                )
        except HTTPError as exc:
            body = exc.read().decode(
                exc.headers.get_content_charset() or "utf-8",
                errors="replace",
            )
            return OfficialArchiveResponse(
                status_code=exc.code,
                final_url=exc.geturl(),
                body=body,
            )


@dataclass(frozen=True)
class _ArchiveLink:
    """Keep one literal anchor target and its visible published label."""

    href: str
    text: str


class _ArchiveHTMLParser(HTMLParser):
    """Collect visible archive text and anchors without executing page scripts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible_text: list[str] = []
        self.links: list[_ArchiveLink] = []
        self._ignored_depth = 0
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if lowered == "a":
            href = dict(attrs).get("href")
            if href:
                self._anchor_href = href
                self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth = max(self._ignored_depth - 1, 0)
            return
        if self._ignored_depth:
            return
        if lowered == "a" and self._anchor_href is not None:
            self.links.append(
                _ArchiveLink(
                    href=self._anchor_href,
                    text=" ".join(" ".join(self._anchor_text).split()),
                )
            )
            self._anchor_href = None
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        self.visible_text.append(cleaned)
        if self._anchor_href is not None:
            self._anchor_text.append(cleaned)


@dataclass(frozen=True)
class _Evidence:
    """Keep a normalised URL with its indexed title and snippet."""

    result_url: str
    title: str
    snippet: str


@dataclass(frozen=True)
class DiscoverySearchAttempt(SearchAttempt):
    """Extend the existing audit record for official and indexed discovery."""

    election_name: str | None = None
    election_year: int | None = None
    division_ward_name: str | None = None
    search_date: str | None = None
    domains_searched: tuple[str, ...] = (SEARCH_DOMAIN,)
    accepted_result_count: int = 0
    excluded_result_count: int = 0
    discovery_method: str = "indexed_search"
    request_url: str | None = None
    discovered_url: str | None = None
    validation_result: str | None = None
    rejection_reason: str | None = None
    discovered_name: str | None = None
    official_name: str | None = None
    name_status: AreaNameStatus | None = None
    metadata_status: MetadataStatus | None = None
    missing_metadata_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ElectionContext:
    """Election metadata supported by a published archive, index or search result."""

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


@dataclass(frozen=True)
class _OfficialDiscovery:
    """Keep official archive areas and their detailed audit independently of search."""

    areas: tuple[DiscoveredElectionArea, ...]
    attempts: tuple[DiscoverySearchAttempt, ...]


def _single_numeric_value(url: str, name: str) -> str | None:
    values = [
        value
        for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True)
        if key == name
    ]
    return values[0] if len(values) == 1 and values[0].isdigit() else None


def _normalise_2026_map_index_url(url: str) -> str:
    """Validate one of the two published 2026 East/West map-index URLs.

    Map indexes have no meaningful query parameters.  Rejecting them here
    keeps discovery tied to the two configured public entry points and avoids
    silently following an altered or unrelated map URL.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string.")
    parsed = urlsplit(url.strip())
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise ValueError("URL must use HTTP or HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain user credentials.")
    if (parsed.hostname or "").casefold() != MAP_INDEX_HOST:
        raise ValueError("URL is not a Surrey 2026 map index URL.")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("URL must not use a non-standard port.")
    if parsed.query:
        raise ValueError("Surrey 2026 map index URLs must not include query parameters.")

    # The official West URL uses a capital W.  Match case-insensitively for a
    # normal web URL, then return one stable spelling for audit and deduplication.
    path = parsed.path if parsed.path.endswith("/") else f"{parsed.path}/"
    canonical_path = MAP_INDEX_PATHS.get(path.casefold())
    if canonical_path is None:
        raise ValueError("URL is not a configured Surrey 2026 map index URL.")
    return urlunsplit(("https", MAP_INDEX_HOST, canonical_path, "", ""))


def _is_2026_map_index_url(url: str) -> bool:
    """Return whether a canonical discovery source uses the 2026 map route."""
    parsed = urlsplit(url)
    return (
        (parsed.hostname or "").casefold() == MAP_INDEX_HOST
        and parsed.path.casefold() in MAP_INDEX_PATHS
    )


def validate_discovery_source_url(url: str) -> str:
    """Accept a historical archive/index or a configured 2026 map index."""
    try:
        return _normalise_2026_map_index_url(url)
    except ValueError:
        pass
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
    """Build deterministic fallback queries for an official archive or area index."""
    canonical_index = validate_discovery_source_url(index_url)
    election_identifier = _election_identifier(canonical_index)
    exact_area_index = (
        "https://mycouncil.surreycc.gov.uk/"
        f"mgElectionElectionAreaResults.aspx?EID={election_identifier}"
    )
    queries = [f'site:mycouncil.surreycc.gov.uk "{canonical_index}"']
    if canonical_index != exact_area_index:
        queries.append(f'site:mycouncil.surreycc.gov.uk "{exact_area_index}"')
    queries.append(
        "site:mycouncil.surreycc.gov.uk "
        f'inurl:mgElectionElectionAreaResults.aspx "EID={election_identifier}"'
    )
    if election_date:
        queries.append(
            "site:mycouncil.surreycc.gov.uk "
            f'inurl:mgElectionAreaResults.aspx "{election_date}"'
        )
    if election_name:
        queries.append(
            f'site:mycouncil.surreycc.gov.uk inurl:mgElectionAreaResults.aspx "{election_name}"'
        )
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


def _canonical_area_name(value: str | None) -> str | None:
    """Apply only whitespace, case and punctuation normalisation for comparison."""
    if not value:
        return None
    cleaned = " ".join(re.sub(r"[^A-Za-z0-9]+", " ", value).casefold().split())
    return cleaned or None


def area_name_status(
    discovered_name: str | None,
    official_name: str | None,
) -> AreaNameStatus:
    """Compare names without silently treating distinct wards as one ward."""
    discovered = _canonical_area_name(discovered_name)
    official = _canonical_area_name(official_name)
    if discovered and official:
        return AreaNameStatus.EXACT if discovered == official else AreaNameStatus.NAME_MISMATCH
    if official:
        return AreaNameStatus.OFFICIAL_ONLY
    return AreaNameStatus.SEARCH_ONLY


def _context_from_text(text: str) -> _ElectionContext:
    """Read only published election labels and dates from visible page text."""
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
    if not name_match:
        return _ElectionContext(None, None, None)
    name = " ".join(name_match.group(1).split())
    year_match = YEAR_PATTERN.search(name)
    date_match = DATE_PATTERN.search(text)
    return _ElectionContext(
        int(year_match.group(1)) if year_match else None,
        name,
        date_match.group(1) if date_match else None,
    )


def _metadata_audit(context: _ElectionContext) -> tuple[MetadataStatus, tuple[str, ...]]:
    """Record missing published metadata without treating a valid URL as invalid."""
    missing_fields = tuple(
        field_name
        for field_name, value in (
            ("election_year", context.year),
            ("election_name", context.name),
        )
        if value is None
    )
    return (
        MetadataStatus.MISSING if missing_fields else MetadataStatus.COMPLETE,
        missing_fields,
    )


def _extract_metadata(results: Iterable[SearchResult]) -> _ElectionContext:
    candidates = []
    for result in results:
        context = _context_from_text(" ".join((result.title, result.snippet)))
        if context.year is not None and context.name is not None:
            candidates.append(context)
    if not candidates:
        return _ElectionContext(None, None, None)
    return sorted(
        candidates,
        key=lambda item: (item.year or 0, (item.name or "").casefold(), item.date or ""),
    )[0]


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
        evidence.setdefault(result_url, []).append(
            _Evidence(result_url=result_url, title=result.title, snippet=result.snippet)
        )
    return evidence


def _best_area_name(items: Iterable[_Evidence]) -> str | None:
    names = {name for item in items if (name := extract_area_name(item.title))}
    if not names:
        return None
    return sorted(names, key=lambda name: (len(name), name.casefold()))[0]


def _parse_archive_page(body: str) -> _ArchiveHTMLParser:
    parser = _ArchiveHTMLParser()
    parser.feed(body)
    parser.close()
    return parser


def _official_area_name(link: _ArchiveLink) -> str | None:
    """Accept a ward label only when the official anchor contains a real name."""
    name = " ".join(link.text.split()).strip()
    if not name or name.casefold() in GENERIC_AREA_LINK_TEXT:
        return None
    return name


def _official_attempt(
    *,
    source_index_url: str,
    request_url: str,
    status: str,
    result_count: int,
    context: _ElectionContext,
    discovered_url: str | None = None,
    division_ward_name: str | None = None,
    validation_result: str | None = None,
    rejection_reason: str | None = None,
    accepted: int = 0,
    excluded: int = 0,
    name_status: AreaNameStatus | None = None,
    discovery_method: str = "official_archive",
) -> DiscoverySearchAttempt:
    """Create one method-labelled official audit record without credentials."""
    metadata_status, missing_metadata_fields = _metadata_audit(context)
    # A 2026 map route reads the published www10 index and follows its literal
    # mycouncil result links.  Store both public hosts in the audit instead of
    # implying that this route was discovered through the historical archive.
    domains_searched = (
        (MAP_INDEX_HOST, SEARCH_DOMAIN)
        if discovery_method == "official_map_index"
        else (SEARCH_DOMAIN,)
    )
    return DiscoverySearchAttempt(
        query="",
        source_index_url=source_index_url,
        status=status,
        result_count=result_count,
        error=rejection_reason if status == "failed" else None,
        election_name=context.name,
        election_year=context.year,
        division_ward_name=division_ward_name,
        search_date=datetime.now(timezone.utc).date().isoformat(),
        domains_searched=domains_searched,
        accepted_result_count=accepted,
        excluded_result_count=excluded,
        discovery_method=discovery_method,
        request_url=request_url,
        discovered_url=discovered_url,
        validation_result=validation_result,
        rejection_reason=rejection_reason,
        discovered_name=division_ward_name,
        official_name=division_ward_name,
        name_status=name_status,
        metadata_status=metadata_status,
        missing_metadata_fields=missing_metadata_fields,
    )


def _result_link_candidates(
    links: Iterable[_ArchiveLink],
    page_url: str,
) -> Iterable[tuple[_ArchiveLink, str]]:
    """Yield only literal official result links published in the current page."""
    for link in links:
        absolute_url = urljoin(page_url, link.href)
        try:
            yield link, normalise_area_result_url(absolute_url)
        except ValueError:
            continue


def _map_result_identifier(result_url: str) -> tuple[str, str] | None:
    """Return a 2026 ward identity only when both official identifiers exist.

    The map may repeat one result page for multiple elected candidates.  The
    EID/ID pair identifies the published result page without treating that
    repetition as either a new ward or evidence about the number of Seats.
    """
    election_id = _single_numeric_value(result_url, "EID")
    result_id = _single_numeric_value(result_url, "ID")
    if election_id is None or result_id is None:
        return None
    return election_id, result_id


def _discover_from_2026_map_index(
    source_index_url: str,
    client: OfficialArchiveClient,
) -> _OfficialDiscovery:
    """Discover 2026 wards from one published East/West map index.

    This is deliberately separate from the historical archive walker.  The
    map page directly links to result pages and has no EID index pagination;
    discovery therefore reads only its literal, labelled result links.
    """
    attempts: list[DiscoverySearchAttempt] = []
    response, error = _fetch_official_page(client, source_index_url)
    empty_context = _ElectionContext(None, None, None)
    if response is None or error:
        attempts.append(
            _official_attempt(
                source_index_url=source_index_url,
                request_url=source_index_url,
                status="failed",
                result_count=0,
                context=empty_context,
                validation_result="unavailable",
                rejection_reason=error or "unavailable",
                discovery_method="official_map_index",
            )
        )
        return _OfficialDiscovery((), tuple(attempts))

    try:
        final_index_url = _normalise_2026_map_index_url(response.final_url)
    except ValueError:
        attempts.append(
            _official_attempt(
                source_index_url=source_index_url,
                request_url=response.final_url,
                status="failed",
                result_count=0,
                context=empty_context,
                validation_result="unexpected_redirect",
                rejection_reason="invalid_map_index_url",
                discovery_method="official_map_index",
            )
        )
        return _OfficialDiscovery((), tuple(attempts))

    parser = _parse_archive_page(response.body)
    # The configured election layer owns the 2026 election name/year.  The map
    # index itself is not required to repeat them, so absence is audited rather
    # than guessed from its URL or from the year-specific adapter.
    context = _context_from_text(" ".join(parser.visible_text))
    areas_by_identifier: dict[tuple[str, str], DiscoveredElectionArea] = {}
    seen_identifiers: set[tuple[str, str]] = set()
    result_link_count = 0

    for link in parser.links:
        literal_url = urljoin(final_index_url, link.href)
        if urlsplit(literal_url).path.casefold() != "/mgElectionAreaResults.aspx".casefold():
            continue
        result_link_count += 1
        try:
            result_url = normalise_area_result_url(literal_url)
        except ValueError:
            attempts.append(
                _official_attempt(
                    source_index_url=source_index_url,
                    request_url=final_index_url,
                    status="completed",
                    result_count=1,
                    context=context,
                    discovered_url=literal_url,
                    validation_result="rejected",
                    rejection_reason="invalid_map_result_url",
                    excluded=1,
                    discovery_method="official_map_index",
                )
            )
            continue

        identifier = _map_result_identifier(result_url)
        if identifier is None:
            attempts.append(
                _official_attempt(
                    source_index_url=source_index_url,
                    request_url=final_index_url,
                    status="completed",
                    result_count=1,
                    context=context,
                    discovered_url=result_url,
                    validation_result="rejected",
                    rejection_reason="missing_map_result_eid_or_id",
                    excluded=1,
                    discovery_method="official_map_index",
                )
            )
            continue

        official_name = _official_area_name(link)
        if official_name is None:
            attempts.append(
                _official_attempt(
                    source_index_url=source_index_url,
                    request_url=final_index_url,
                    status="completed",
                    result_count=1,
                    context=context,
                    discovered_url=result_url,
                    validation_result="rejected",
                    rejection_reason="missing_official_area_name",
                    excluded=1,
                    discovery_method="official_map_index",
                )
            )
            continue

        if identifier in seen_identifiers:
            attempts.append(
                _official_attempt(
                    source_index_url=source_index_url,
                    request_url=final_index_url,
                    status="completed",
                    result_count=1,
                    context=context,
                    discovered_url=result_url,
                    division_ward_name=official_name,
                    validation_result="duplicate",
                    rejection_reason="duplicate_result_url",
                    excluded=1,
                    name_status=area_name_status(official_name, official_name),
                    discovery_method="official_map_index",
                )
            )
            continue

        seen_identifiers.add(identifier)
        metadata_status, missing_metadata_fields = _metadata_audit(context)
        name_status = area_name_status(official_name, official_name)
        areas_by_identifier[identifier] = DiscoveredElectionArea(
            election_year=context.year,
            election_name=context.name,
            division_ward_name=official_name,
            result_url=result_url,
            source_index_url=source_index_url,
            discovery_status=DiscoveryStatus.DISCOVERED,
            discovered_name=official_name,
            official_name=official_name,
            name_status=name_status,
            discovery_method="official_map_index",
            official_index_url=final_index_url,
            metadata_status=metadata_status,
            missing_metadata_fields=missing_metadata_fields,
        )
        attempts.append(
            _official_attempt(
                source_index_url=source_index_url,
                request_url=final_index_url,
                status="completed",
                result_count=1,
                context=context,
                discovered_url=result_url,
                division_ward_name=official_name,
                validation_result=(
                    "accepted_metadata_missing"
                    if metadata_status is MetadataStatus.MISSING
                    else "accepted"
                ),
                accepted=1,
                name_status=name_status,
                discovery_method="official_map_index",
            )
        )

    # Keep one index-level audit row even when no candidate result links exist.
    attempts.insert(
        0,
        _official_attempt(
            source_index_url=source_index_url,
            request_url=final_index_url,
            status="completed",
            result_count=result_link_count,
            context=context,
            validation_result="map_index_loaded",
            discovery_method="official_map_index",
        ),
    )
    return _OfficialDiscovery(
        tuple(
            sorted(
                areas_by_identifier.values(),
                key=lambda area: (area.division_ward_name or "").casefold(),
            )
        ),
        tuple(attempts),
    )


def _index_link_candidates(
    links: Iterable[_ArchiveLink],
    page_url: str,
    election_identifier: str,
) -> Iterable[str]:
    """Yield only official area-index links that retain the target election ID."""
    for link in links:
        try:
            candidate = validate_index_url(urljoin(page_url, link.href))
        except ValueError:
            continue
        if _single_numeric_value(candidate, "EID") == election_identifier:
            yield candidate


def _fetch_official_page(
    client: OfficialArchiveClient,
    url: str,
) -> tuple[OfficialArchiveResponse | None, str | None]:
    """Fetch once and surface a compact audit error instead of retrying or bypassing."""
    try:
        response = client.fetch(url)
    except Exception as exc:
        return None, type(exc).__name__
    if not 200 <= response.status_code < 300:
        return response, f"HTTP_{response.status_code}"
    return response, None


def _discover_from_official_archive(
    source_index_url: str,
    client: OfficialArchiveClient,
) -> _OfficialDiscovery:
    """Follow only published archive/index links and never construct area URLs."""
    election_identifier = _election_identifier(source_index_url)
    attempts: list[DiscoverySearchAttempt] = []
    # RPID and XXR are display parameters. A result ID is the stable published
    # election-area identity within one official index, so it prevents the
    # same ward appearing again through a different pagination/display link.
    areas_by_result_id: dict[str, DiscoveredElectionArea] = {}
    attempted_result_ids: set[str] = set()

    source_response, source_error = _fetch_official_page(client, source_index_url)
    if source_response is None or source_error:
        attempts.append(
            _official_attempt(
                source_index_url=source_index_url,
                request_url=source_index_url,
                status="failed",
                result_count=0,
                context=_ElectionContext(None, None, None),
                validation_result="unavailable",
                rejection_reason=source_error or "unavailable",
            )
        )
        return _OfficialDiscovery((), tuple(attempts))

    source_parser = _parse_archive_page(source_response.body)
    source_context = _context_from_text(" ".join(source_parser.visible_text))
    source_final_url = validate_discovery_source_url(source_response.final_url)
    source_is_area_index = urlsplit(source_final_url).path.casefold() == INDEX_PATH.casefold()
    # An area-index URL can be supplied directly.  When an archive URL is
    # supplied, only the archive's literal same-election link starts the next
    # step; the program never constructs an area-index URL from an EID.
    pending_indexes = {
        source_final_url
    } if source_is_area_index else set(
        _index_link_candidates(
            source_parser.links,
            source_final_url,
            election_identifier,
        )
    )

    # A direct result link on an archive page is rare but still valid official
    # evidence when its visible name and archive election context are present.
    attempts.append(
        _official_attempt(
            source_index_url=source_index_url,
            request_url=source_final_url,
            status="completed",
            result_count=len(pending_indexes),
            context=source_context,
            validation_result="area_index_found" if pending_indexes else "no_area_index",
            accepted=len(pending_indexes),
        )
    )

    processed_indexes: set[str] = set()
    while pending_indexes:
        # Stable order keeps the first retained published link deterministic.
        index_url = min(pending_indexes)
        pending_indexes.remove(index_url)
        if index_url in processed_indexes:
            continue
        processed_indexes.add(index_url)
        if source_is_area_index and index_url == source_final_url:
            parser = source_parser
            context = source_context
            final_index_url = source_final_url
        else:
            response, error = _fetch_official_page(client, index_url)
            if response is None or error:
                attempts.append(
                    _official_attempt(
                        source_index_url=source_index_url,
                        request_url=index_url,
                        status="failed",
                        result_count=0,
                        context=source_context,
                        validation_result="unavailable",
                        rejection_reason=error or "unavailable",
                    )
                )
                continue
            final_index_url = validate_index_url(response.final_url)
            parser = _parse_archive_page(response.body)
            parsed_context = _context_from_text(" ".join(parser.visible_text))
            # Prefer election metadata printed on this area-index page.  The
            # archive metadata remains a fallback only when the index omits it.
            context = parsed_context if parsed_context.name else source_context
            attempts.append(
                _official_attempt(
                    source_index_url=source_index_url,
                    request_url=final_index_url,
                    status="completed",
                    result_count=0,
                    context=context,
                    validation_result="area_index_loaded",
                )
            )

        # Following only same-EID index links covers a published pagination
        # structure while avoiding generated page numbers or unrelated elections.
        for next_index in _index_link_candidates(
            parser.links,
            final_index_url,
            election_identifier,
        ):
            if next_index not in processed_indexes:
                pending_indexes.add(next_index)

        for link, result_url in _result_link_candidates(parser.links, final_index_url):
            official_name = _official_area_name(link)
            result_id = _single_numeric_value(result_url, "ID")
            if result_id is None:
                # normalise_area_result_url already requires a numeric ID, but
                # retain an explicit rejection if a future URL rule changes.
                attempts.append(
                    _official_attempt(
                        source_index_url=source_index_url,
                        request_url=final_index_url,
                        status="completed",
                        result_count=1,
                        context=context,
                        discovered_url=result_url,
                        division_ward_name=official_name,
                        validation_result="rejected",
                        rejection_reason="missing_result_identifier",
                        excluded=1,
                    )
                )
                continue
            if result_id in attempted_result_ids:
                attempts.append(
                    _official_attempt(
                        source_index_url=source_index_url,
                        request_url=final_index_url,
                        status="completed",
                        result_count=1,
                        context=context,
                        discovered_url=result_url,
                        division_ward_name=official_name,
                        validation_result="duplicate",
                        rejection_reason="duplicate_result_url",
                        excluded=1,
                        name_status=area_name_status(official_name, official_name),
                    )
                )
                continue
            attempted_result_ids.add(result_id)
            if official_name is None:
                attempts.append(
                    _official_attempt(
                        source_index_url=source_index_url,
                        request_url=final_index_url,
                        status="completed",
                        result_count=1,
                        context=context,
                        discovered_url=result_url,
                        validation_result="rejected",
                        rejection_reason="missing_official_area_name",
                        excluded=1,
                    )
                )
                continue
            name_status = area_name_status(official_name, official_name)
            metadata_status, missing_metadata_fields = _metadata_audit(context)
            areas_by_result_id[result_id] = DiscoveredElectionArea(
                election_year=context.year,
                election_name=context.name,
                division_ward_name=official_name,
                result_url=result_url,
                source_index_url=source_index_url,
                discovery_status=DiscoveryStatus.DISCOVERED,
                discovered_name=official_name,
                official_name=official_name,
                name_status=name_status,
                discovery_method="official_archive",
                official_index_url=final_index_url,
                metadata_status=metadata_status,
                missing_metadata_fields=missing_metadata_fields,
            )
            attempts.append(
                _official_attempt(
                    source_index_url=source_index_url,
                    request_url=final_index_url,
                    status="completed",
                    result_count=1,
                    context=context,
                    discovered_url=result_url,
                    division_ward_name=official_name,
                    validation_result=(
                        "accepted_metadata_missing"
                        if metadata_status is MetadataStatus.MISSING
                        else "accepted"
                    ),
                    accepted=1,
                    name_status=name_status,
                )
            )

    return _OfficialDiscovery(
        tuple(
            sorted(
                areas_by_result_id.values(),
                key=lambda area: (area.division_ward_name or "").casefold(),
            )
        ),
        tuple(attempts),
    )


def _discover_from_indexed_search(
    canonical_index: str,
    provider: SearchProvider,
    prior_attempts: Iterable[DiscoverySearchAttempt] = (),
) -> DiscoveryReport:
    """Keep the existing SerpAPI route as a lower-priority audited fallback."""
    # This function is reached only when the official route produced no valid
    # result areas.  Search evidence therefore cannot overwrite official URLs
    # or published ward names when those are already available.
    search_runs: list[_SearchRun] = []
    all_results: list[SearchResult] = []

    initial_queries = build_search_queries(canonical_index)
    for query in initial_queries:
        try:
            results = tuple(provider.search(query))
        except Exception as exc:
            search_runs.append(_SearchRun(query, (), type(exc).__name__))
            continue
        search_runs.append(_SearchRun(query, results))
        all_results.extend(results)

    context = _extract_metadata(all_results)
    if context.name or context.date:
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
    metadata_status, missing_metadata_fields = _metadata_audit(context)
    for result_url in sorted(evidence_by_url):
        area_name = _best_area_name(evidence_by_url[result_url])
        if area_name is None:
            status = DiscoveryStatus.MISSING_AREA_NAME
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
                discovered_name=area_name,
                official_name=None,
                name_status=area_name_status(area_name, None),
                discovery_method="indexed_search",
                metadata_status=metadata_status,
                missing_metadata_fields=missing_metadata_fields,
            )
        )

    search_date = datetime.now(timezone.utc).date().isoformat()
    accepted_urls = set(evidence_by_url)
    attempts = list(prior_attempts)
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
                discovery_method="indexed_search",
                validation_result="search_fallback",
                metadata_status=metadata_status,
                missing_metadata_fields=missing_metadata_fields,
            )
        )
    return DiscoveryReport(canonical_index, tuple(areas), tuple(attempts))


def discover_election_areas(
    index_url: str,
    provider: SearchProvider,
    *,
    archive_client: OfficialArchiveClient | None = None,
    indexed_search_only: bool = False,
) -> DiscoveryReport:
    """Discover election areas with an explicit source strategy.

    ``indexed_search_only`` is used by the Streamlit application specified by
    the supervisor. It avoids making direct council-page access a requirement
    and keeps SerpAPI as the application's discovery provider. Existing audited
    research pipelines retain the official-first default.
    """
    canonical_index = validate_discovery_source_url(index_url)
    if indexed_search_only:
        return _discover_from_indexed_search(canonical_index, provider)
    if _is_2026_map_index_url(canonical_index):
        # Map indexes are a complete official source in their own right.  Do
        # not use the historical search fallback: it cannot safely add wards
        # that the East/West map has not explicitly published.
        official = _discover_from_2026_map_index(
            canonical_index,
            archive_client or UrllibOfficialArchiveClient(),
        )
        return DiscoveryReport(canonical_index, official.areas, official.attempts)
    official = _discover_from_official_archive(
        canonical_index,
        archive_client or UrllibOfficialArchiveClient(),
    )
    if official.areas:
        return DiscoveryReport(canonical_index, official.areas, official.attempts)
    # One unavailable or rejected link does not trigger a mixed-source result.
    # Fallback is used only after the complete official attempt has no accepted
    # areas, keeping the provenance of each discovery run unambiguous.
    return _discover_from_indexed_search(canonical_index, provider, official.attempts)
