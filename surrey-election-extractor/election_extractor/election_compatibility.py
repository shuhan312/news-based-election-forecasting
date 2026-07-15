"""Read-only compatibility checks for configured Surrey elections."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from election_extractor.election_config import ElectionConfiguration
from election_extractor.official_source import parse_official_election_page


class CompatibilityStatus(str, Enum):
    """Describe whether existing pipeline stages can be used without changes."""

    COMPATIBLE = "compatible"
    COMPATIBLE_WITH_METADATA = "compatible_with_metadata"
    REQUIRES_CHANGES = "requires_changes"


@dataclass(frozen=True)
class CompatibilityPageResponse:
    """Represent one public page response used only for diagnostic inspection."""

    status_code: int | None
    final_url: str | None
    body: str
    error: str | None = None


class CompatibilityPageClient(Protocol):
    """Allow real public HTTP and mocked page responses to use one checker."""

    def fetch(self, url: str) -> CompatibilityPageResponse:
        """Fetch one page without browser automation or protection bypassing."""


class UrllibCompatibilityPageClient:
    """Use ordinary public HTTP only when a caller elects to run a live check."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self._timeout = timeout

    def fetch(self, url: str) -> CompatibilityPageResponse:
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "SurreyElectionExtractor/1.0 (compatibility audit)",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                body = response.read().decode(
                    response.headers.get_content_charset() or "utf-8",
                    errors="replace",
                )
                return CompatibilityPageResponse(
                    status_code=response.getcode(),
                    final_url=response.geturl(),
                    body=body,
                )
        except HTTPError as error:
            return CompatibilityPageResponse(
                status_code=error.code,
                final_url=error.geturl(),
                body=error.read().decode(
                    error.headers.get_content_charset() or "utf-8",
                    errors="replace",
                ),
                error=type(error).__name__,
            )
        except (URLError, OSError) as error:
            return CompatibilityPageResponse(
                status_code=None,
                final_url=None,
                body="",
                error=type(error).__name__,
            )


@dataclass(frozen=True)
class ArchiveCompatibility:
    """Record whether the configured official archive page is usable as evidence."""

    status: str
    url: str
    expected_election_information_present: bool
    evidence: str


@dataclass(frozen=True)
class DiscoveryCompatibility:
    """Summarise result-link discovery without creating election-area records."""

    result_pages_found: int
    raw_result_links_found: int
    duplicate_urls_removed: int
    failed_urls: int
    url_patterns: tuple[str, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class ResultStructureCompatibility:
    """Describe fields observed in representative official result-page HTML."""

    representative_pages_inspected: int
    candidate_fields_available: Mapping[str, bool]
    summary_fields_available: Mapping[str, bool]
    missing_candidate_fields: tuple[str, ...]
    missing_summary_fields: tuple[str, ...]
    html_table_patterns: tuple[str, ...]


@dataclass(frozen=True)
class MetadataCompatibility:
    """Record Seats provenance needs without assigning a Seats value."""

    seats_source: str
    supplementary_metadata_required: bool
    evidence: str


@dataclass(frozen=True)
class ElectionCompatibilityReport:
    """Provide a serialisable, audit-only compatibility decision for one election."""

    election_id: str
    election_year: int
    election_name: str
    election_type: str
    archive_url: str
    overall_status: CompatibilityStatus
    archive: ArchiveCompatibility
    discovery: DiscoveryCompatibility
    result_structure: ResultStructureCompatibility
    metadata: MetadataCompatibility
    risks: tuple[str, ...]
    recommendation: str
    provenance: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        """Return JSON-ready data while preserving enum values as readable text."""
        output = asdict(self)
        output["overall_status"] = self.overall_status.value
        return output


class _ArchiveHTMLParser(HTMLParser):
    """Collect visible text and href values without interpreting election records."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.visible_text: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag.casefold() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self._ignored_depth = max(self._ignored_depth - 1, 0)

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = " ".join(data.split())
        if cleaned:
            self.visible_text.append(cleaned)


CANDIDATE_FIELDS = {
    "candidate_name": "candidate name",
    "original_party_name": "party name",
    "votes_received": "votes",
    "vote_share": "vote share",
    "outcome": "elected status",
}
SUMMARY_FIELDS = {
    "number_of_seats": "seats",
    "total_votes": "total votes",
    "electorate": "electorate",
    "ballot_papers_issued": "ballot papers issued",
    "ballot_papers_rejected": "rejected ballots",
    "turnout": "turnout",
}


def _valid_public_url(url: str) -> bool:
    """Check URL shape only; this check never makes a network request."""
    parsed = urlsplit(url)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
    )


def _official_surrey_domain(url: str) -> bool:
    """Accept only Surrey County Council public subdomains for result links."""
    hostname = (urlsplit(url).hostname or "").casefold()
    return hostname == "surreycc.gov.uk" or hostname.endswith(".surreycc.gov.uk")


def _looks_like_legacy_result_page(url: str) -> bool:
    """Recognise the result-page route already supported by the current pipeline."""
    parsed = urlsplit(url)
    if parsed.path.casefold() != "/mgelectionarearesults.aspx":
        return False
    identifiers = [value for key, value in parse_qsl(parsed.query) if key.casefold() == "id"]
    return len(identifiers) == 1 and identifiers[0].isdigit()


def _normalise_discovered_url(url: str) -> str:
    """Normalise equivalent discovery links only for compatibility counting."""
    parsed = urlsplit(url)
    parameters = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            parsed.path,
            urlencode(parameters),
            "",
        )
    )


def _archive_page_has_expected_election_information(
    text: str, configuration: ElectionConfiguration
) -> bool:
    """Require visible election context, not an assumed URL-to-year relationship."""
    lowered = text.casefold()
    return str(configuration.election_year) in lowered and "election" in lowered


def _discover_result_urls(
    archive_url: str, archive_body: str
) -> tuple[tuple[str, ...], int, tuple[str, ...], tuple[str, ...]]:
    """Inspect archive links and report unsupported or non-official patterns."""
    parser = _ArchiveHTMLParser()
    parser.feed(archive_body)
    parser.close()

    raw_result_links = []
    issues = []
    for href in parser.hrefs:
        absolute_url = urljoin(archive_url, href)
        if not _looks_like_legacy_result_page(absolute_url):
            continue
        raw_result_links.append(absolute_url)
        if not _official_surrey_domain(absolute_url):
            issues.append(f"Non-Surrey result-page domain: {absolute_url}")

    unique_urls = tuple(dict.fromkeys(_normalise_discovered_url(url) for url in raw_result_links))
    patterns = tuple(sorted({urlsplit(url).path for url in unique_urls}))
    return unique_urls, len(raw_result_links), patterns, tuple(issues)


def _inspect_result_structure(
    result_urls: Sequence[str], client: CompatibilityPageClient, sample_size: int
) -> tuple[ResultStructureCompatibility, tuple[str, ...], tuple[str, ...]]:
    """Inspect a bounded representative sample without extracting candidate records."""
    observed_candidate_fields: set[str] = set()
    observed_summary_fields: set[str] = set()
    patterns = []
    issues = []
    inspected_urls = []

    for result_url in result_urls[:sample_size]:
        response = client.fetch(result_url)
        if response.status_code != 200:
            issues.append(f"Representative result page unavailable: {result_url}")
            continue
        inspected_urls.append(result_url)
        page_data = parse_official_election_page(response.body)
        row_fields = {
            field_name
            for row in page_data.candidate_rows
            for field_name, _ in row.fields
        }
        shared_fields = {field_name for field_name, _ in page_data.shared_fields}
        observed_candidate_fields.update(row_fields)
        observed_summary_fields.update(shared_fields)
        patterns.append(
            f"{result_url}: candidate_rows={len(page_data.candidate_rows)}; "
            f"voting_summary_label={'yes' if 'voting summary' in response.body.casefold() else 'no'}"
        )

    candidate_available = {
        label: field_name in observed_candidate_fields
        for field_name, label in CANDIDATE_FIELDS.items()
    }
    summary_available = {
        label: field_name in observed_summary_fields
        for field_name, label in SUMMARY_FIELDS.items()
    }
    missing_candidate = tuple(label for label, available in candidate_available.items() if not available)
    missing_summary = tuple(label for label, available in summary_available.items() if not available)
    return (
        ResultStructureCompatibility(
            representative_pages_inspected=len(inspected_urls),
            candidate_fields_available=candidate_available,
            summary_fields_available=summary_available,
            missing_candidate_fields=missing_candidate,
            missing_summary_fields=missing_summary,
            html_table_patterns=tuple(patterns),
        ),
        tuple(issues),
        tuple(inspected_urls),
    )


def _recommendation(status: CompatibilityStatus) -> str:
    """Return a bounded next action without starting extraction."""
    if status is CompatibilityStatus.COMPATIBLE:
        return "A later, separately approved extraction run can use the existing pipeline."
    if status is CompatibilityStatus.COMPATIBLE_WITH_METADATA:
        return (
            "Do not extract yet. First prepare approved supplementary election-structure metadata "
            "for official Seats fields that are not published."
        )
    return (
        "Do not extract yet. Review the listed archive, discovery or page-structure risks before "
        "changing the pipeline."
    )


def check_election_compatibility(
    configuration: ElectionConfiguration,
    client: CompatibilityPageClient,
    *,
    sample_size: int = 3,
) -> ElectionCompatibilityReport:
    """Produce a read-only compatibility report for one configured election."""
    if sample_size < 1:
        raise ValueError("sample_size must be at least 1.")

    if not _valid_public_url(configuration.official_url):
        archive = ArchiveCompatibility(
            status="invalid_url",
            url=configuration.official_url,
            expected_election_information_present=False,
            evidence="The configured official URL is not an absolute public HTTP(S) URL.",
        )
        discovery = DiscoveryCompatibility(0, 0, 0, 0, (), ("Invalid archive URL.",))
        structure = ResultStructureCompatibility(0, {}, {}, (), (), ())
        metadata = MetadataCompatibility("not_checked", False, "Archive was not inspected.")
        return ElectionCompatibilityReport(
            configuration.election_id,
            configuration.election_year,
            configuration.election_name,
            configuration.election_type,
            configuration.official_url,
            CompatibilityStatus.REQUIRES_CHANGES,
            archive,
            discovery,
            structure,
            metadata,
            ("Invalid archive URL.",),
            _recommendation(CompatibilityStatus.REQUIRES_CHANGES),
            {"configuration_url": configuration.official_url},
        )

    archive_response = client.fetch(configuration.official_url)
    visible_parser = _ArchiveHTMLParser()
    visible_parser.feed(archive_response.body)
    visible_parser.close()
    expected_information = _archive_page_has_expected_election_information(
        " ".join(visible_parser.visible_text), configuration
    )
    archive_accessible = archive_response.status_code == 200 and bool(archive_response.body)
    archive = ArchiveCompatibility(
        status="accessible" if archive_accessible else "unavailable",
        url=configuration.official_url,
        expected_election_information_present=expected_information,
        evidence=(
            f"HTTP status={archive_response.status_code}; expected election information "
            f"present={'yes' if expected_information else 'no'}; error={archive_response.error or 'none'}."
        ),
    )
    if not archive_accessible:
        discovery = DiscoveryCompatibility(0, 0, 0, 0, (), ("Archive page is unavailable.",))
        structure = ResultStructureCompatibility(0, {}, {}, (), (), ())
        metadata = MetadataCompatibility("not_checked", False, "Archive was unavailable.")
        return ElectionCompatibilityReport(
            configuration.election_id,
            configuration.election_year,
            configuration.election_name,
            configuration.election_type,
            configuration.official_url,
            CompatibilityStatus.REQUIRES_CHANGES,
            archive,
            discovery,
            structure,
            metadata,
            ("Archive page is unavailable.",),
            _recommendation(CompatibilityStatus.REQUIRES_CHANGES),
            {"archive_url": configuration.official_url},
        )

    result_urls, raw_count, patterns, discovery_issues = _discover_result_urls(
        configuration.official_url, archive_response.body
    )
    discovery = DiscoveryCompatibility(
        result_pages_found=len(result_urls),
        raw_result_links_found=raw_count,
        duplicate_urls_removed=raw_count - len(result_urls),
        failed_urls=0,
        url_patterns=patterns,
        issues=discovery_issues,
    )
    structure, structure_issues, inspected_urls = _inspect_result_structure(
        result_urls, client, sample_size
    )

    risks = list(discovery_issues) + list(structure_issues)
    if not expected_information:
        risks.append("Archive page does not visibly contain the configured election year and election context.")
    if not result_urls:
        risks.append("No result-page links matching the current discovery URL format were found.")
    if structure.missing_candidate_fields:
        risks.append(
            "Representative pages are missing candidate fields: "
            + ", ".join(structure.missing_candidate_fields)
            + "."
        )

    seats_observed = structure.summary_fields_available.get("seats", False)
    metadata = MetadataCompatibility(
        seats_source="official_result_page" if seats_observed else "not_observed_in_representative_pages",
        supplementary_metadata_required=not seats_observed,
        evidence=(
            "Seats was observed in a representative official Voting Summary."
            if seats_observed
            else (
                "Seats was not observed in the representative official pages. No Seats value was "
                "created; approved supplementary metadata may be required after a full audit."
            )
        ),
    )
    if metadata.supplementary_metadata_required:
        risks.append("Official Seats was not observed; supplementary metadata may be required.")
    non_seat_summary_missing = [
        field_name for field_name in structure.missing_summary_fields if field_name != "seats"
    ]
    if non_seat_summary_missing:
        risks.append(
            "Representative pages are missing Voting Summary fields: "
            + ", ".join(non_seat_summary_missing)
            + "."
        )

    base_incompatible = (
        not expected_information
        or not result_urls
        or bool(structure.missing_candidate_fields)
        or bool(structure_issues)
    )
    status = (
        CompatibilityStatus.REQUIRES_CHANGES
        if base_incompatible
        else (
            CompatibilityStatus.COMPATIBLE_WITH_METADATA
            if metadata.supplementary_metadata_required
            else CompatibilityStatus.COMPATIBLE
        )
    )
    return ElectionCompatibilityReport(
        configuration.election_id,
        configuration.election_year,
        configuration.election_name,
        configuration.election_type,
        configuration.official_url,
        status,
        archive,
        discovery,
        structure,
        metadata,
        tuple(risks),
        _recommendation(status),
        {
            "archive_url": configuration.official_url,
            "representative_result_page_urls": inspected_urls,
            "inspection_mode": "read_only_representative_html",
        },
    )


def write_compatibility_reports(
    report: ElectionCompatibilityReport, output_directory: str | Path
) -> tuple[Path, Path]:
    """Write JSON and Markdown compatibility reports without changing source data."""
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / f"{report.election_id}_compatibility.json"
    markdown_path = output_path / f"{report.election_id}_compatibility.md"
    json_path.write_text(json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8")

    candidate_fields = report.result_structure.candidate_fields_available
    summary_fields = report.result_structure.summary_fields_available
    lines = [
        f"# Election Compatibility Report: {report.election_name}",
        "",
        "## Election",
        "",
        f"- Election ID: {report.election_id}",
        f"- Year: {report.election_year}",
        f"- Type: {report.election_type}",
        f"- Archive URL: {report.archive_url}",
        "",
        "## Compatibility",
        "",
        f"- Overall status: {report.overall_status.value}",
        f"- Recommendation: {report.recommendation}",
        "",
        "## Archive and discovery",
        "",
        f"- Archive status: {report.archive.status}",
        f"- Archive evidence: {report.archive.evidence}",
        f"- Result pages found: {report.discovery.result_pages_found}",
        f"- Duplicate URLs removed: {report.discovery.duplicate_urls_removed}",
        f"- URL patterns: {', '.join(report.discovery.url_patterns) or 'none'}",
        "",
        "## Result page structure",
        "",
        f"- Candidate fields available: {dict(candidate_fields)}",
        f"- Summary fields available: {dict(summary_fields)}",
        f"- HTML/table patterns: {' | '.join(report.result_structure.html_table_patterns) or 'none'}",
        "",
        "## Seats metadata",
        "",
        f"- Seats source: {report.metadata.seats_source}",
        f"- Supplementary metadata required: {report.metadata.supplementary_metadata_required}",
        f"- Evidence: {report.metadata.evidence}",
        "",
        "## Risks",
        "",
    ]
    lines.extend(f"- {risk}" for risk in report.risks) if report.risks else lines.append("- None observed.")
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            f"- Archive source: {report.provenance.get('archive_url', report.provenance.get('configuration_url'))}",
            "- Representative result pages: "
            + ", ".join(report.provenance.get("representative_result_page_urls", ())),
            f"- Inspection mode: {report.provenance.get('inspection_mode', 'configuration_validation_only')}",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path
