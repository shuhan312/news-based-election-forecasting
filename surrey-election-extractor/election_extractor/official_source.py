"""Normal public-HTTP diagnostics for official Surrey election result pages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from html.parser import HTMLParser
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

from election_extractor.url_utils import normalise_area_result_url


class OfficialPageClassification(str, Enum):
    """Describe what a normal HTTP request returned without bypassing protection."""

    VALID_ELECTION_RESULT_PAGE = "valid_election_result_page"
    EMPTY_PAGE = "empty_page"
    PROTECTION_PAGE = "protection_page"
    UNRELATED_PAGE = "unrelated_page"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class OfficialPageResponse:
    """Represent the public HTTP response needed for diagnosis and parsing."""

    status_code: int
    final_url: str
    body: str
    # Provenance of the served copy. A live request keeps the default value;
    # an archived official copy records exactly which public capture supplied
    # the page so the workbook audit can cite it. These fields default so that
    # every existing client and test fixture remains valid without changes.
    retrieval_source: str = "live_official_page"
    archive_snapshot_url: str | None = None
    archive_snapshot_timestamp: str | None = None


class OfficialPageClient(Protocol):
    """Allow real HTTP access and deterministic mocked responses to share a contract."""

    def fetch(self, url: str) -> OfficialPageResponse:
        """Fetch one official result URL using ordinary public HTTP access."""


class UrllibOfficialPageClient:
    """Use Python's standard HTTP client without browser automation or bypasses."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self._timeout = timeout

    def fetch(self, url: str) -> OfficialPageResponse:
        canonical_url = normalise_area_result_url(url)
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
                return OfficialPageResponse(
                    status_code=response.getcode(),
                    final_url=response.geturl(),
                    body=body,
                )
        except HTTPError as exc:
            # HTTP error pages are still evidence for the diagnostic. Reading
            # their public response body does not retry or bypass protection.
            body = exc.read().decode(
                exc.headers.get_content_charset() or "utf-8",
                errors="replace",
            )
            return OfficialPageResponse(
                status_code=exc.code,
                final_url=exc.geturl(),
                body=body,
            )


@dataclass(frozen=True)
class OfficialPageDiagnostic:
    """Store an auditable classification without retaining the full page body."""

    source_url: str
    status_code: int | None
    final_url: str | None
    page_title: str | None
    content_length: int
    classification: OfficialPageClassification
    diagnostic_timestamp: str
    error: str | None = None
    # Copied from the response so the extraction log can state whether the
    # page came from the live council site or a lawful archived copy, and can
    # cite the exact capture. ``None`` keeps older diagnostics unchanged.
    retrieval_source: str | None = None
    archive_snapshot_url: str | None = None
    archive_snapshot_timestamp: str | None = None


@dataclass(frozen=True)
class OfficialPageFetchResult:
    """Keep the page body in memory while exposing a body-free audit record."""

    diagnostic: OfficialPageDiagnostic
    body: str | None


@dataclass(frozen=True)
class OfficialCandidateRow:
    """Store one exact official table row before typed record conversion."""

    fields: tuple[tuple[str, str], ...]
    evidence_text: str


@dataclass(frozen=True)
class _OfficialHTMLTable:
    """Keep table rows together with the official label that identifies the table."""

    rows: tuple[tuple[tuple[str, str], ...], ...]
    caption: str
    summary_attribute: str


@dataclass(frozen=True)
class OfficialPageData:
    """Return published shared fields and evidence-backed candidate rows."""

    shared_fields: tuple[tuple[str, str], ...]
    shared_evidence: tuple[tuple[str, str], ...]
    candidate_rows: tuple[OfficialCandidateRow, ...]


class _ElectionHTMLParser(HTMLParser):
    """Collect page title, visible text and simple HTML tables conservatively."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page_title = ""
        self.visible_text: list[str] = []
        self.tables: list[_OfficialHTMLTable] = []
        self._table: list[list[tuple[str, str]]] | None = None
        self._table_caption: list[str] = []
        self._table_summary_attribute = ""
        self._row: list[tuple[str, str]] | None = None
        self._cell_tag: str | None = None
        self._cell_text: list[str] = []
        self._title_depth = 0
        self._caption_depth = 0
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if lowered == "title":
            self._title_depth += 1
        elif lowered == "table" and self._table is None:
            self._table = []
            self._table_caption = []
            self._table_summary_attribute = dict(attrs).get("summary") or ""
        elif lowered == "caption" and self._table is not None:
            self._caption_depth += 1
        elif lowered == "tr" and self._table is not None:
            self._row = []
        elif lowered in {"th", "td"} and self._row is not None:
            self._cell_tag = lowered
            self._cell_text = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth = max(self._ignored_depth - 1, 0)
            return
        if self._ignored_depth:
            return
        if lowered == "title":
            self._title_depth = max(self._title_depth - 1, 0)
        elif lowered == "caption" and self._caption_depth:
            self._caption_depth = max(self._caption_depth - 1, 0)
        elif lowered in {"th", "td"} and self._cell_tag == lowered:
            text = " ".join(" ".join(self._cell_text).split())
            if self._row is not None:
                self._row.append((lowered, text))
            self._cell_tag = None
            self._cell_text = []
        elif lowered == "tr" and self._row is not None:
            if self._table is not None and any(text for _, text in self._row):
                self._table.append(self._row)
            self._row = None
        elif lowered == "table" and self._table is not None:
            self.tables.append(
                _OfficialHTMLTable(
                    rows=tuple(tuple(row) for row in self._table),
                    caption=" ".join(" ".join(self._table_caption).split()),
                    summary_attribute=self._table_summary_attribute,
                )
            )
            self._table = None
            self._table_caption = []
            self._table_summary_attribute = ""

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        self.visible_text.append(cleaned)
        if self._title_depth:
            self.page_title = " ".join((self.page_title, cleaned)).strip()
        if self._caption_depth:
            self._table_caption.append(cleaned)
        if self._cell_tag:
            self._cell_text.append(cleaned)


PROTECTION_MARKERS = (
    "incapsula",
    "access denied",
    "request unsuccessful",
    "_incapsula_resource",
    "verify you are human",
    "security check",
    "captcha",
    "challenge page",
)


def _parse_html(body: str) -> _ElectionHTMLParser:
    parser = _ElectionHTMLParser()
    parser.feed(body)
    parser.close()
    return parser


def _normalise_heading(value: str) -> str:
    return " ".join(
        "".join(character.casefold() if character.isalnum() else " " for character in value).split()
    )


def _has_candidate_table(parser: _ElectionHTMLParser) -> bool:
    for table in parser.tables:
        for row in table.rows:
            headings = {_normalise_heading(text) for _, text in row}
            if (
                headings & {"candidate", "election candidate"}
                and "party" in headings
                and "votes" in headings
            ):
                return True
    return False


def _is_voting_summary_table(table: _OfficialHTMLTable) -> bool:
    """Accept only a table explicitly labelled as Surrey's Voting Summary."""
    descriptor = _normalise_heading(
        f"{table.caption} {table.summary_attribute}"
    )
    # The caption/summary attribute is published by ModernGov. Requiring that
    # label prevents similarly shaped tables, such as rejected-ballot details,
    # from being misread as the election-level voting summary.
    if "voting summary" not in descriptor:
        return False
    return any(
        {_normalise_heading(text) for _, text in row} >= {"details", "number"}
        for row in table.rows
    )


def _same_official_result_page(requested_url: str, final_url: str) -> bool:
    """Accept a normal redirect only when it retains the same official result ID."""
    try:
        requested = normalise_area_result_url(requested_url)
        final = normalise_area_result_url(final_url)
    except ValueError:
        return False

    def result_id(url: str) -> str | None:
        values = [
            value
            for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True)
            if key == "ID"
        ]
        return values[0] if len(values) == 1 else None

    # ModernGov can add a harmless display parameter after a normal redirect.
    # The requested and final pages are equivalent only when their published
    # official result identifiers still match; a redirect cannot change wards.
    return result_id(requested) == result_id(final)


def _candidate_header_field(text: str) -> str | None:
    """Map visible table headers, including ModernGov's literal '%' heading."""
    if text.strip() == "%":
        return "vote_share"
    return CANDIDATE_HEADERS.get(_normalise_heading(text))


def fetch_and_diagnose_official_page(
    url: str,
    client: OfficialPageClient,
    *,
    diagnostic_timestamp: str | None = None,
) -> OfficialPageFetchResult:
    """Fetch and classify one official URL without retries or protection bypasses."""
    canonical_url = normalise_area_result_url(url)
    timestamp = diagnostic_timestamp or datetime.now(timezone.utc).isoformat()
    try:
        response = client.fetch(canonical_url)
    except Exception as exc:
        diagnostic = OfficialPageDiagnostic(
            source_url=canonical_url,
            status_code=None,
            final_url=None,
            page_title=None,
            content_length=0,
            classification=OfficialPageClassification.UNAVAILABLE,
            diagnostic_timestamp=timestamp,
            error=type(exc).__name__,
        )
        return OfficialPageFetchResult(diagnostic, None)
    return diagnose_official_response(
        canonical_url,
        response,
        diagnostic_timestamp=timestamp,
    )


def diagnose_official_response(
    canonical_url: str,
    response: OfficialPageResponse,
    *,
    diagnostic_timestamp: str | None = None,
) -> OfficialPageFetchResult:
    """Classify one already-fetched official response into an audit diagnostic.

    This is separated from :func:`fetch_and_diagnose_official_page` so a
    layered client can classify its live response before deciding whether an
    archived official copy is needed, without issuing a second HTTP request.
    """
    timestamp = diagnostic_timestamp or datetime.now(timezone.utc).isoformat()
    body = response.body or ""
    parser = _parse_html(body)
    visible = " ".join(parser.visible_text)
    lower_page = f"{parser.page_title} {visible} {body}".casefold()
    content_length = len(body.encode("utf-8"))
    try:
        final_url = normalise_area_result_url(response.final_url)
    except ValueError:
        final_url = response.final_url

    if not body.strip():
        classification = OfficialPageClassification.EMPTY_PAGE
    elif response.status_code in {401, 403, 429} or any(
        marker in lower_page for marker in PROTECTION_MARKERS
    ):
        classification = OfficialPageClassification.PROTECTION_PAGE
    elif (
        200 <= response.status_code < 300
        and _same_official_result_page(canonical_url, final_url)
        and "election results for" in lower_page
        and _has_candidate_table(parser)
    ):
        classification = OfficialPageClassification.VALID_ELECTION_RESULT_PAGE
    else:
        classification = OfficialPageClassification.UNRELATED_PAGE

    diagnostic = OfficialPageDiagnostic(
        source_url=canonical_url,
        status_code=response.status_code,
        final_url=final_url,
        page_title=parser.page_title or None,
        content_length=content_length,
        classification=classification,
        diagnostic_timestamp=timestamp,
        # ``getattr`` tolerates minimal protocol implementations (test doubles
        # or third-party clients) that predate the provenance fields.
        retrieval_source=getattr(response, "retrieval_source", None),
        archive_snapshot_url=getattr(response, "archive_snapshot_url", None),
        archive_snapshot_timestamp=getattr(
            response, "archive_snapshot_timestamp", None
        ),
    )
    return OfficialPageFetchResult(diagnostic, body)


CANDIDATE_HEADERS = {
    "candidate": "candidate_name",
    "election candidate": "candidate_name",
    "party": "original_party_name",
    "votes": "votes_received",
    "vote share": "vote_share",
    "percentage": "vote_share",
    "outcome": "outcome",
    "position": "final_position",
    "final position": "final_position",
    "elected": "elected",
}

SUMMARY_LABELS = {
    "seats": "number_of_seats",
    "number of seats": "number_of_seats",
    "total votes": "total_votes",
    "valid votes": "valid_votes",
    "electorate": "electorate",
    "ballot papers issued": "ballot_papers_issued",
    "number of ballot papers issued": "ballot_papers_issued",
    "ballot papers rejected": "ballot_papers_rejected",
    "number of ballot papers rejected": "ballot_papers_rejected",
    "rejected ballots": "ballot_papers_rejected",
    "turnout": "turnout",
    "winning candidate": "winning_candidate",
    "winning party": "winning_party",
    "winning margin": "winning_margin",
}


def parse_official_election_page(body: str) -> OfficialPageData:
    """Parse only explicitly labelled fields from a valid official HTML page."""
    parser = _parse_html(body)
    visible_text = " ".join(parser.visible_text)
    shared: dict[str, str] = {}
    evidence: dict[str, str] = {}

    title_match = re.search(
        r"Election results for\s+(.+?),\s*(\d{1,2}\s+[A-Za-z]+\s+(?:19|20)\d{2})",
        parser.page_title or visible_text,
        re.IGNORECASE,
    )
    if title_match:
        shared["division_ward_name"] = " ".join(title_match.group(1).split())
        shared["election_date"] = " ".join(title_match.group(2).split())
        evidence["division_ward_name"] = title_match.group(0)
        evidence["election_date"] = title_match.group(0)

    election_match = re.search(
        # Principal-election pages use the published plural "Elections",
        # while by-election pages use singular "Election".  Accepting the
        # optional final "s" preserves both official forms and prevents every
        # principal-election candidate from being marked incomplete solely
        # because of a heading variation.
        r"(County Council\s+(?:By-)?Elections?\s+(?:19|20)\d{2})",
        visible_text,
        re.IGNORECASE,
    )
    if election_match:
        shared["election_name"] = " ".join(election_match.group(1).split())
        evidence["election_name"] = election_match.group(0)
    if "surrey county council" in visible_text.casefold():
        shared["authority"] = "Surrey County Council"
        evidence["authority"] = "Surrey County Council"

    candidates: list[OfficialCandidateRow] = []
    for table in parser.tables:
        header_index = None
        header_fields: list[str | None] = []
        for index, row in enumerate(table.rows):
            mapped = [_candidate_header_field(text) for _, text in row]
            if {item for item in mapped if item} >= {
                "candidate_name",
                "original_party_name",
                "votes_received",
            }:
                header_index = index
                header_fields = mapped
                break
        if header_index is not None:
            for row in table.rows[header_index + 1 :]:
                values: dict[str, str] = {}
                for field_name, (_, text) in zip(header_fields, row):
                    cleaned = " ".join(text.split()).strip()
                    if field_name and cleaned:
                        if field_name == "vote_share" and cleaned == "%":
                            continue
                        values[field_name] = cleaned
                if values.get("candidate_name"):
                    candidates.append(
                        OfficialCandidateRow(
                            fields=tuple(values.items()),
                            evidence_text=" | ".join(text for _, text in row if text),
                        )
                    )

    for table in parser.tables:
        if not _is_voting_summary_table(table):
            continue
        # Summary fields are accepted only from the table explicitly labelled
        # "Voting Summary" on the official page. Values remain published text
        # here; numeric conversion happens later in the existing extraction
        # pipeline without using calculated substitutes.
        for row in table.rows:
            if len(row) < 2:
                continue
            label = _normalise_heading(row[0][1])
            field_name = SUMMARY_LABELS.get(label)
            value = " ".join(row[1][1].split()).strip()
            if field_name and value:
                shared[field_name] = value
                evidence[field_name] = f"{row[0][1]}: {row[1][1]}"

    return OfficialPageData(
        shared_fields=tuple(shared.items()),
        shared_evidence=tuple(evidence.items()),
        candidate_rows=tuple(candidates),
    )
