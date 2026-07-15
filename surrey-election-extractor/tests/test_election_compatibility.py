"""Tests for the read-only reusable election compatibility checker."""

from dataclasses import replace

from election_extractor.election_compatibility import (
    CompatibilityPageResponse,
    CompatibilityStatus,
    check_election_compatibility,
    check_configured_election_compatibility,
    write_compatibility_reports,
)
from election_extractor.election_config import load_election_config
from election_extractor.discovery import OfficialArchiveResponse
from election_extractor.search_providers.mock_provider import MockSearchProvider


ARCHIVE_URL = "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=16&RPID=0"
RESULT_URL = "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=258&RPID=0"
INDEX_URL = "https://mycouncil.surreycc.gov.uk/mgElectionElectionAreaResults.aspx?EID=16&RPID=1"


class MockCompatibilityPageClient:
    """Return deterministic archive and result HTML without any live requests."""

    def __init__(self, pages: dict[str, CompatibilityPageResponse]) -> None:
        self.pages = pages
        self.requests: list[str] = []

    def fetch(self, url: str) -> CompatibilityPageResponse:
        self.requests.append(url)
        return self.pages[url]


class MockDiscoveryArchiveClient:
    """Return official archive fixtures to exercise the existing discovery stage."""

    def __init__(self, pages: dict[str, OfficialArchiveResponse]) -> None:
        self.pages = pages

    def fetch(self, url: str) -> OfficialArchiveResponse:
        return self.pages[url]


def configured_2021():
    """Use the actual configured 2021 entry as the test input."""
    return next(
        item
        for item in load_election_config()
        if item.election_id == "surrey-county-council-2021"
    )


def archive_html() -> str:
    """Provide a minimal archive with duplicate result links for deduplication checks."""
    return f"""
    <html><body>
      <h1>County Council Election 2021</h1>
      <a href=\"{RESULT_URL}\">Addlestone</a>
      <a href=\"{RESULT_URL}#duplicate\">Addlestone duplicate</a>
    </body></html>
    """


def result_html(*, include_seats: bool = True) -> str:
    """Provide representative official table labels without creating extracted records."""
    seats_row = "<tr><td>Seats</td><td>1</td></tr>" if include_seats else ""
    return f"""
    <html><body>
      <table>
        <tr><th>Election Candidate</th><th>Party</th><th>Votes</th><th>Vote Share</th><th>Outcome</th></tr>
        <tr><td>Example Candidate</td><td>Example Party</td><td>100</td><td>50%</td><td>Elected</td></tr>
      </table>
      <table summary=\"Voting summary table\">
        <caption>Voting Summary</caption>
        <tr><th>Details</th><th>Number</th></tr>
        {seats_row}
        <tr><td>Total votes</td><td>100</td></tr>
        <tr><td>Electorate</td><td>200</td></tr>
        <tr><td>Number of ballot papers issued</td><td>100</td></tr>
        <tr><td>Number of ballot papers rejected</td><td>0</td></tr>
        <tr><td>Turnout</td><td>50%</td></tr>
      </table>
    </body></html>
    """


def client_for(*, include_seats: bool = True) -> MockCompatibilityPageClient:
    return MockCompatibilityPageClient(
        {
            ARCHIVE_URL: CompatibilityPageResponse(200, ARCHIVE_URL, archive_html()),
            RESULT_URL: CompatibilityPageResponse(200, RESULT_URL, result_html(include_seats=include_seats)),
        }
    )


def discovery_archive_client() -> MockDiscoveryArchiveClient:
    """Provide an archive and an area index with one published result-page URL."""
    archive_body = f"""
    <html><body>
      <h1>County Council Election 2021 - Thursday, 6 May 2021</h1>
      <a href=\"{INDEX_URL}\">Election results by wards</a>
    </body></html>
    """
    index_body = f"""
    <html><body>
      <h1>County Council Election 2021 - Thursday, 6 May 2021</h1>
      <a href=\"{RESULT_URL}\">Addlestone</a>
    </body></html>
    """
    return MockDiscoveryArchiveClient(
        {
            ARCHIVE_URL: OfficialArchiveResponse(200, ARCHIVE_URL, archive_body),
            INDEX_URL: OfficialArchiveResponse(200, INDEX_URL, index_body),
        }
    )


def test_valid_election_configuration_returns_compatible_status() -> None:
    report = check_election_compatibility(configured_2021(), client_for())

    assert report.overall_status is CompatibilityStatus.COMPATIBLE
    assert report.discovery.result_pages_found == 1
    assert report.discovery.duplicate_urls_removed == 1
    assert all(report.result_structure.candidate_fields_available.values())
    assert all(report.result_structure.summary_fields_available.values())


def test_configured_checker_reuses_existing_official_discovery() -> None:
    report = check_configured_election_compatibility(
        configured_2021(),
        MockSearchProvider({}),
        discovery_archive_client(),
        client_for(),
    )

    assert report.overall_status is CompatibilityStatus.COMPATIBLE
    assert report.discovery.result_pages_found == 1
    assert report.discovery.unique_divisions_found == 1
    assert report.provenance["inspection_mode"] == (
        "read_only_existing_discovery_and_representative_html"
    )
    assert report.structural_differences_from_2021 == (
        "No candidate or non-Seats Voting Summary field difference was observed in the representative pages.",
    )


def test_invalid_archive_url_is_detected_without_fetching() -> None:
    configuration = replace(configured_2021(), official_url="not-an-http-url")
    client = client_for()

    report = check_election_compatibility(configuration, client)

    assert report.overall_status is CompatibilityStatus.REQUIRES_CHANGES
    assert report.archive.status == "invalid_url"
    assert client.requests == []


def test_missing_summary_fields_are_reported_not_filled() -> None:
    report = check_election_compatibility(configured_2021(), client_for(include_seats=False))

    assert report.overall_status is CompatibilityStatus.COMPATIBLE_WITH_METADATA
    assert report.result_structure.summary_fields_available["seats"] is False
    assert "seats" in report.result_structure.missing_summary_fields
    assert report.metadata.supplementary_metadata_required is True
    assert report.metadata.seats_source == "not_observed_in_representative_pages"


def test_checker_never_creates_a_seat_assumption() -> None:
    report = check_election_compatibility(configured_2021(), client_for(include_seats=False))
    metadata = report.as_dict()["metadata"]

    assert "secondary_number_of_seats" not in metadata
    assert "assumed_seats" not in metadata
    assert "No Seats value was created" in report.metadata.evidence


def test_reports_include_provenance_and_are_written(tmp_path) -> None:
    report = check_election_compatibility(configured_2021(), client_for())

    json_path, markdown_path = write_compatibility_reports(report, tmp_path)

    assert json_path.exists()
    assert markdown_path.exists()
    assert ARCHIVE_URL in json_path.read_text(encoding="utf-8")
    assert RESULT_URL in markdown_path.read_text(encoding="utf-8")
