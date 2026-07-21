"""Fallback that reads a lawful archived copy when the official page is blocked.

The live council site (mycouncil.surreycc.gov.uk) is sitting behind Imperva
Incapsula bot protection, so a plain HTTP request almost always gets back a
tiny JavaScript challenge page (HTTP 200, only a few hundred bytes) instead of
the actual result tables. That is a problem for this project because SerpAPI
snippets alone are not detailed enough to ever satisfy the strict `Complete`
rule (Google's title/snippet text almost never includes the full candidate
table or the voting summary), which is why the workbook kept showing
`Complete: 0` even when discovery and extraction were otherwise working fine.

I checked and the Internet Archive's Wayback Machine already has a full
HTTP-200 capture for every 2013/2017/2021 official area-result and index page
(confirmed against the public CDX index before writing any of this), so this
module reads the *same official URL* from its Wayback snapshot instead of
retrying the live site. This is not scraping around Incapsula in any way -
no request is ever sent to the council site to get past its protection, the
archive is a separate, independent, already-public copy of the same page.
Every value taken from a snapshot is tagged with the exact capture timestamp
and the `web.archive.org` URL so it stays traceable in the Extraction Log.

`ArchiveFallbackOfficialPageClient` and `ArchiveFallbackOfficialArchiveClient`
below implement the same client interfaces the rest of the app already used
(`OfficialPageClient` / `OfficialArchiveClient`), so nothing in discovery,
extraction, validation or workbook generation needed to change. For any given
page the order is simply: try the live page once, fall back to its Wayback
snapshot if that failed, and if even the archive has nothing, let the
existing indexed-search fallback in workflow.py take over as before.
"""

from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from election_extractor.discovery import (
    OfficialArchiveResponse,
    UrllibOfficialArchiveClient,
    validate_discovery_source_url,
)
from election_extractor.official_source import (
    OfficialPageClassification,
    OfficialPageResponse,
    PROTECTION_MARKERS,
    UrllibOfficialPageClient,
    diagnose_official_response,
)
from election_extractor.url_utils import normalise_area_result_url


# The CDX API is the Wayback Machine's public capture index. It returns, for
# one URL, every stored capture with its 14-digit UTC timestamp. The ``id_``
# flag on a replay URL returns the original archived bytes without the
# Wayback toolbar or link rewriting, which keeps the existing HTML parser
# behaviour identical to a live fetch.
WAYBACK_CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
WAYBACK_RAW_SNAPSHOT_TEMPLATE = "https://web.archive.org/web/{timestamp}id_/{url}"

# Requesting a far-future timestamp makes the Wayback replay service redirect
# to the capture closest to it — that is, the newest stored capture. This
# "fast path" resolves and serves a page in one request, where the CDX index
# needs one slow query per URL variant plus a second request for the body.
NEWEST_CAPTURE_HINT = "20991231235959"

# Matches the effective URL after the replay redirect, e.g.
# https://web.archive.org/web/20210228064005id_/https://mycouncil....
_REPLAY_URL_PATTERN = re.compile(
    r"^https?://web\.archive\.org/web/(\d{14})[a-z_]*/(.+)$"
)

# Provenance label copied into OfficialPageResponse/OfficialPageDiagnostic and
# from there into the workbook's extraction log.
ARCHIVED_OFFICIAL_COPY = "archived_official_copy_wayback_machine"

_USER_AGENT = "SurreyElectionExtractor/1.0 (academic data audit)"


class ArchivedSnapshotNotFoundError(RuntimeError):
    """No usable public capture exists for the requested official URL."""


@dataclass(frozen=True)
class WaybackCapture:
    """Identify one public capture of an official URL.

    ``original_url`` is the URL exactly as the crawler recorded it (it may
    include a harmless ModernGov ``RPID`` display parameter). ``timestamp`` is
    the Wayback 14-digit UTC capture time. ``snapshot_url`` is the raw-bytes
    replay address used for the actual fetch and cited in the audit log.
    """

    original_url: str
    timestamp: str
    snapshot_url: str

    @property
    def iso_timestamp(self) -> str:
        """Render the 14-digit capture time as readable ISO-8601 UTC."""
        raw = self.timestamp
        if len(raw) != 14 or not raw.isdigit():
            return raw
        return (
            f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
            f"T{raw[8:10]}:{raw[10:12]}:{raw[12:14]}Z"
        )


class WaybackHTTPClient(Protocol):
    """Allow real Wayback HTTP access and deterministic test doubles."""

    def get(self, url: str) -> tuple[int, str, str]:
        """Return ``(status_code, final_url, body_text)`` for one public URL."""


class UrllibWaybackHTTPClient:
    """Fetch public Wayback URLs with bounded retry for transient errors.

    The supervisor prompt requires exponential backoff for temporary
    rate-limit and network errors, and forbids indefinite retrying. Retries
    apply only to the public Internet Archive service, never to the protected
    council site.
    """

    # Four retries with 1s/2s/4s/8s backoff (worst case ~15s beyond the first
    # attempt) rides out the short rate-limit bursts observed in live testing
    # when many sequential requests are needed (walking a paginated official
    # index, or the preflight's own sample checks right after that walk),
    # while remaining bounded rather than indefinite.
    _RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        max_attempts: int = 5,
        min_request_interval: float = 1.0,
    ) -> None:
        self._timeout = timeout
        self._max_attempts = max(1, max_attempts)
        # An 81-area run issues Wayback requests in quick succession. Without
        # pacing the archive intermittently rate-limits the sequence, which
        # turned individual wards into transient failures in live testing.
        # One request per second keeps a full election run reliable and is a
        # courteous load for a free public service.
        self._min_request_interval = max(0.0, min_request_interval)
        self._last_request_time = 0.0

    def get(self, url: str) -> tuple[int, str, str]:
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            if attempt:
                # Exponential backoff: 1s, 2s, 4s, 8s. Bounded by max_attempts.
                time.sleep(2 ** (attempt - 1))
            pacing_wait = (
                self._last_request_time + self._min_request_interval - time.monotonic()
            )
            if pacing_wait > 0:
                time.sleep(pacing_wait)
            self._last_request_time = time.monotonic()
            try:
                request = Request(
                    url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,text/plain",
                        "User-Agent": _USER_AGENT,
                    },
                )
                with urlopen(request, timeout=self._timeout) as response:
                    body = response.read().decode(
                        response.headers.get_content_charset() or "utf-8",
                        errors="replace",
                    )
                    return response.getcode(), response.geturl(), body
            except HTTPError as exc:
                if exc.code in self._RETRYABLE_STATUS and attempt + 1 < self._max_attempts:
                    last_error = exc
                    continue
                # A non-retryable HTTP error page is still a valid observation
                # (e.g. 404 = no capture); return it instead of raising.
                body = exc.read().decode(
                    exc.headers.get_content_charset() or "utf-8",
                    errors="replace",
                )
                return exc.code, exc.geturl(), body
            except URLError as exc:
                last_error = exc
                if attempt + 1 < self._max_attempts:
                    continue
                raise
        # Defensive: the loop either returned or raised; keep type-checkers
        # satisfied without hiding an unexpected control-flow change.
        raise last_error if last_error else RuntimeError("Wayback fetch failed")


def _capture_lookup_keys(canonical_url: str) -> tuple[str, ...]:
    """Return equivalent URL keys under which a capture may be stored.

    ModernGov appends an ``RPID`` display parameter that does not change the
    published result page (``RPID=0`` is its null form). Crawlers recorded the
    same page under keys with and without that parameter, so the resolver
    checks the exact URL, the URL without ``RPID`` and the URL with
    ``RPID=0``. No other parameter is added or removed: ``EID``/``ID`` remain
    exactly as submitted because they identify the election and ward.
    """
    split = urlsplit(canonical_url)
    parameters = parse_qsl(split.query, keep_blank_values=True)

    def rebuild(params: list[tuple[str, str]]) -> str:
        return urlunsplit(
            (split.scheme, split.netloc, split.path, urlencode(params), "")
        )

    without_rpid = [
        (name, value) for name, value in parameters if name.casefold() != "rpid"
    ]
    keys = [canonical_url, rebuild(without_rpid), rebuild([*without_rpid, ("RPID", "0")])]
    # Preserve priority order (exact URL first) while removing duplicates.
    return tuple(dict.fromkeys(keys))


def _looks_like_protection_capture(body: str) -> bool:
    """Detect a capture where the crawler itself archived a challenge stub."""
    lowered = body.casefold()
    return any(marker in lowered for marker in PROTECTION_MARKERS)


class WaybackSnapshotResolver:
    """Resolve one official URL to its usable public captures, newest first.

    Newest-first is a deliberate policy: an official result page is a static
    record, and the most recent capture reflects any correction the council
    later published. Captures whose stored body is itself a protection stub
    are skipped by the client, which is why several candidates are returned.

    Lookup keys are tried in priority order (exact URL first) and the first
    key with any capture supplies the result, because every key is an
    equivalent form of the same official page. Results are cached for the
    lifetime of the resolver so preflight and extraction never repeat the
    same slow CDX query within one run.
    """

    def __init__(
        self,
        http_client: WaybackHTTPClient | None = None,
        *,
        max_captures: int = 5,
    ) -> None:
        self._http = http_client or UrllibWaybackHTTPClient()
        self._max_captures = max(1, max_captures)
        self._cache: dict[str, tuple[WaybackCapture, ...]] = {}

    def captures(self, canonical_url: str) -> tuple[WaybackCapture, ...]:
        if canonical_url in self._cache:
            return self._cache[canonical_url]
        result: tuple[WaybackCapture, ...] = ()
        for key in _capture_lookup_keys(canonical_url):
            found: dict[tuple[str, str], WaybackCapture] = {}
            for timestamp, original in self._cdx_rows(key):
                # CDX stores some originals HTML-entity encoded (``&amp;``).
                # Decode before building the replay URL and the audit trail.
                original_url = html.unescape(original)
                identity = (timestamp, original_url)
                if identity in found:
                    continue
                found[identity] = WaybackCapture(
                    original_url=original_url,
                    timestamp=timestamp,
                    snapshot_url=WAYBACK_RAW_SNAPSHOT_TEMPLATE.format(
                        timestamp=timestamp,
                        url=original_url,
                    ),
                )
            if found:
                ordered = sorted(
                    found.values(),
                    key=lambda item: item.timestamp,
                    reverse=True,
                )
                result = tuple(ordered[: self._max_captures])
                break
        self._cache[canonical_url] = result
        return result

    def _cdx_rows(self, url_key: str) -> tuple[tuple[str, str], ...]:
        """Query the public CDX index for HTTP-200 captures of one URL key."""
        query = urlencode(
            {
                "url": url_key,
                "output": "json",
                # Only successful captures can contain the published tables.
                "filter": "statuscode:200",
                "fl": "timestamp,original",
                "limit": "200",
            },
            quote_via=quote,
        )
        try:
            status, _, body = self._http.get(f"{WAYBACK_CDX_ENDPOINT}?{query}")
        except Exception:
            # CDX unavailability is not an application error here: the caller
            # simply finds no capture and the workflow keeps its indexed-search
            # fallback. The page-level diagnostic records UNAVAILABLE.
            return ()
        if status != 200 or not body.strip():
            return ()
        try:
            rows = json.loads(body)
        except ValueError:
            return ()
        # The first row of a CDX JSON response is the column-header row.
        return tuple(
            (str(row[0]), str(row[1]))
            for row in rows[1:]
            if isinstance(row, (list, tuple)) and len(row) >= 2
        )


def _capture_from_replay_url(effective_url: str, requested_key: str) -> WaybackCapture:
    """Build the audit capture record from the replay service's final URL.

    After the fast-path request, the effective URL contains the real capture
    timestamp (for example ``/web/20210228064005id_/https://mycouncil...``).
    If the service ever returns an unexpected URL shape, the requested key is
    retained so the citation still identifies what was fetched.
    """
    match = _REPLAY_URL_PATTERN.match(effective_url)
    if match:
        return WaybackCapture(
            original_url=html.unescape(match.group(2)),
            timestamp=match.group(1),
            snapshot_url=effective_url,
        )
    return WaybackCapture(
        original_url=requested_key,
        timestamp=NEWEST_CAPTURE_HINT,
        snapshot_url=effective_url,
    )


def _fetch_archived_copy(
    canonical_url: str,
    resolver: WaybackSnapshotResolver,
    http_client: WaybackHTTPClient,
) -> tuple[WaybackCapture, str]:
    """Return the newest usable capture body for one official URL.

    Fast path first: one replay request per equivalent URL key redirects
    straight to the newest capture and returns its body. The slower CDX
    enumeration runs only when a probe proved that captures exist but the
    newest one is unusable (for example the crawler archived the protection
    stub); it then tries a bounded, newest-first list of older captures.
    When every probe reports no capture at all, the CDX index would agree, so
    it is not queried — this keeps un-archived pagination variants cheap.
    Raises ``ArchivedSnapshotNotFoundError`` when no usable capture exists, so
    the caller's diagnostics record the page as unavailable instead of empty.
    """
    archived_but_unusable = False
    for key in _capture_lookup_keys(canonical_url):
        probe_url = WAYBACK_RAW_SNAPSHOT_TEMPLATE.format(
            timestamp=NEWEST_CAPTURE_HINT,
            url=key,
        )
        try:
            status, effective_url, body = http_client.get(probe_url)
        except Exception:
            # A network failure says nothing about whether captures exist,
            # so the CDX fallback below stays available.
            archived_but_unusable = True
            continue
        if status in {404, 410}:
            # The replay service is authoritative for "no capture stored".
            continue
        if not 200 <= status < 300:
            # Rate limiting or a server error is not evidence of absence.
            archived_but_unusable = True
            continue
        if not body.strip() or _looks_like_protection_capture(body):
            archived_but_unusable = True
            continue
        return _capture_from_replay_url(effective_url, key), body

    if not archived_but_unusable:
        raise ArchivedSnapshotNotFoundError(
            "No archived official copy exists for this URL."
        )

    for capture in resolver.captures(canonical_url):
        try:
            status, _, body = http_client.get(capture.snapshot_url)
        except Exception:
            continue
        if not 200 <= status < 300 or not body.strip():
            continue
        if _looks_like_protection_capture(body):
            continue
        return capture, body
    raise ArchivedSnapshotNotFoundError(
        "No usable archived official copy was found for this URL."
    )


class WaybackOfficialPageClient:
    """Serve one official ward/division result page from a public capture.

    Successful responses are cached by canonical URL for the lifetime of the
    client. Preflight samples pages that extraction fetches again moments
    later; the cache means each archived page is downloaded exactly once per
    run, which keeps the run fast and courteous to the public archive.
    """

    def __init__(
        self,
        http_client: WaybackHTTPClient | None = None,
        *,
        resolver: WaybackSnapshotResolver | None = None,
    ) -> None:
        self._http = http_client or UrllibWaybackHTTPClient()
        self._resolver = resolver or WaybackSnapshotResolver(self._http)
        self._cache: dict[str, OfficialPageResponse] = {}

    def fetch(self, url: str) -> OfficialPageResponse:
        canonical_url = normalise_area_result_url(url)
        cached = self._cache.get(canonical_url)
        if cached is not None:
            return cached
        capture, body = _fetch_archived_copy(
            canonical_url,
            self._resolver,
            self._http,
        )
        try:
            final_url = normalise_area_result_url(capture.original_url)
        except ValueError:
            final_url = capture.original_url
        response = OfficialPageResponse(
            status_code=200,
            final_url=final_url,
            body=body,
            retrieval_source=ARCHIVED_OFFICIAL_COPY,
            archive_snapshot_url=capture.snapshot_url,
            archive_snapshot_timestamp=capture.iso_timestamp,
        )
        self._cache[canonical_url] = response
        return response


class WaybackOfficialArchiveClient:
    """Serve one official election archive/index page from a public capture.

    Responses are cached by canonical URL exactly as in
    :class:`WaybackOfficialPageClient`, because discovery revisits the same
    index pages when walking published pagination links.
    """

    def __init__(
        self,
        http_client: WaybackHTTPClient | None = None,
        *,
        resolver: WaybackSnapshotResolver | None = None,
    ) -> None:
        self._http = http_client or UrllibWaybackHTTPClient()
        self._resolver = resolver or WaybackSnapshotResolver(self._http)
        self._cache: dict[str, OfficialArchiveResponse] = {}

    def fetch(self, url: str) -> OfficialArchiveResponse:
        canonical_url = validate_discovery_source_url(url)
        cached = self._cache.get(canonical_url)
        if cached is not None:
            return cached
        capture, body = _fetch_archived_copy(
            canonical_url,
            self._resolver,
            self._http,
        )
        try:
            final_url = validate_discovery_source_url(capture.original_url)
        except ValueError:
            final_url = capture.original_url
        response = OfficialArchiveResponse(
            status_code=200,
            final_url=final_url,
            body=body,
        )
        self._cache[canonical_url] = response
        return response


class ArchiveFallbackOfficialPageClient:
    """Try the live official result page once, then the archived official copy.

    The live attempt is a single ordinary public request. After the first
    protection response the client stops contacting the live site for the rest
    of the run: repeating a request that the site has already declined would
    add load without adding evidence, and the archived copies are already the
    authoritative fallback. This is deliberately *not* a bypass — the archive
    is a separate lawful publisher of the same official record.
    """

    def __init__(
        self,
        live_client: UrllibOfficialPageClient | None = None,
        archive_client: WaybackOfficialPageClient | None = None,
    ) -> None:
        self._live = live_client or UrllibOfficialPageClient()
        self._archive = archive_client or WaybackOfficialPageClient()
        self._live_blocked = False

    def fetch(self, url: str) -> OfficialPageResponse:
        canonical_url = normalise_area_result_url(url)
        live_response: OfficialPageResponse | None = None
        if not self._live_blocked:
            try:
                live_response = self._live.fetch(canonical_url)
            except Exception:
                live_response = None
            if live_response is not None:
                classification = diagnose_official_response(
                    canonical_url,
                    live_response,
                ).diagnostic.classification
                if (
                    classification
                    is OfficialPageClassification.VALID_ELECTION_RESULT_PAGE
                ):
                    return live_response
                if classification is OfficialPageClassification.PROTECTION_PAGE:
                    self._live_blocked = True
        try:
            return self._archive.fetch(canonical_url)
        except Exception:
            if live_response is not None:
                # Keep the live observation (usually the protection page) so
                # the diagnostic honestly reports why no data was served.
                return live_response
            raise


class ArchiveFallbackOfficialArchiveClient:
    """Try the live archive/index page once, then the archived official copy.

    Index pages have no candidate table, so ``VALID_ELECTION_RESULT_PAGE``
    cannot be required here; a live index response is accepted when it is a
    successful, non-empty page without protection markers.
    """

    def __init__(
        self,
        live_client: UrllibOfficialArchiveClient | None = None,
        archive_client: WaybackOfficialArchiveClient | None = None,
    ) -> None:
        self._live = live_client or UrllibOfficialArchiveClient()
        self._archive = archive_client or WaybackOfficialArchiveClient()
        self._live_blocked = False

    def fetch(self, url: str) -> OfficialArchiveResponse:
        canonical_url = validate_discovery_source_url(url)
        live_response: OfficialArchiveResponse | None = None
        if not self._live_blocked:
            try:
                live_response = self._live.fetch(canonical_url)
            except Exception:
                live_response = None
            if live_response is not None:
                served = (
                    200 <= live_response.status_code < 300
                    and bool(live_response.body.strip())
                    and not _looks_like_protection_capture(live_response.body)
                )
                if served:
                    return live_response
                if _looks_like_protection_capture(live_response.body):
                    self._live_blocked = True
        try:
            return self._archive.fetch(canonical_url)
        except Exception:
            if live_response is not None:
                return live_response
            raise
