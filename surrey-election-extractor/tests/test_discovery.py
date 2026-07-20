"""Unit tests for indexed Surrey election-area discovery."""

import httpx

import pytest

from election_extractor.discovery import (
    OfficialArchiveResponse,
    area_name_status,
    build_search_queries,
    discover_election_areas,
)
from election_extractor.models import (
    AreaNameStatus,
    DiscoveryStatus,
    MetadataStatus,
    SearchResult,
)
from election_extractor.search_providers.mock_provider import MockSearchProvider
from election_extractor.search_providers.serpapi import SerpApiSearchProvider
from election_extractor.url_utils import (
    normalise_area_result_url,
    principal_election_url_to_index_url,
    validate_index_url,
)


INDEX_URL = "https://mycouncil.surreycc.gov.uk/mgElectionElectionAreaResults.aspx?EID=16"
ARCHIVE_URL = "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=16&RPID=0"
ELECTION_NAME = "2021 Surrey County Council election"
OFFICIAL_INDEX_URL = (
    "https://mycouncil.surreycc.gov.uk/"
    "mgElectionElectionAreaResults.aspx?EID=16&RPID=453690863"
)
EAST_2026_MAP_INDEX = "https://www10.surreycc.gov.uk/electionmap/eastSurrey/"
WEST_2026_MAP_INDEX = "https://www10.surreycc.gov.uk/electionmap/WestSurrey/"


class MockOfficialArchiveClient:
    """Return configured public-page fixtures without a live HTTP request."""

    def __init__(
        self,
        responses: dict[str, OfficialArchiveResponse | Exception] | Exception,
    ) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def fetch(self, url: str) -> OfficialArchiveResponse:
        self.urls.append(url)
        if isinstance(self.responses, Exception):
            raise self.responses
        response = self.responses.get(url, RuntimeError(f"Unexpected URL: {url}"))
        if isinstance(response, Exception):
            raise response
        return response


def unavailable_archive_client() -> MockOfficialArchiveClient:
    return MockOfficialArchiveClient(TimeoutError("archive unavailable"))


def search_fallback_report(index_url: str, provider: MockSearchProvider):
    return discover_election_areas(
        index_url,
        provider,
        archive_client=unavailable_archive_client(),
    )


def mocked_provider() -> MockSearchProvider:
    initial_queries = build_search_queries(INDEX_URL)
    metadata_query = build_search_queries(INDEX_URL, ELECTION_NAME)[-1]
    return MockSearchProvider(
        {
            initial_queries[0]: [
                SearchResult(
                    title=f"{ELECTION_NAME} - Surrey County Council",
                    url=INDEX_URL,
                    snippet="Official indexed election results.",
                )
            ],
            initial_queries[1]: [
                SearchResult(
                    title="Election results for Addlestone, 6 May 2021",
                    url=(
                        "http://mycouncil.surreycc.gov.uk/"
                        "mgElectionAreaResults.aspx?utm_source=test&RPID=0&ID=201"
                    ),
                    snippet="2021 Surrey County Council election.",
                ),
                SearchResult(
                    title="Ash - Election results - Surrey County Council",
                    url=(
                        "https://mycouncil.surreycc.gov.uk/"
                        "mgElectionAreaResults.aspx?ID=202&RPID=0"
                    ),
                    snippet="2021 Surrey County Council election.",
                ),
            ],
            metadata_query: [
                SearchResult(
                    title="Election results for Addlestone, 6 May 2021",
                    url=(
                        "https://mycouncil.surreycc.gov.uk/"
                        "mgElectionAreaResults.aspx?ID=201&RPID=0&gclid=tracking"
                    ),
                    snippet="2021 Surrey County Council election.",
                )
            ],
        }
    )


def test_valid_surrey_election_index_url_is_accepted() -> None:
    assert validate_index_url(INDEX_URL) == INDEX_URL


@pytest.mark.parametrize(
    ("landing_url", "expected_eid"),
    [
        (
            "https://mycouncil.surreycc.gov.uk/"
            "mgElectionResults.aspx?ID=5&RPID=0",
            5,
        ),
        (
            "https://mycouncil.surreycc.gov.uk/"
            "mgElectionResults.aspx?ID=10&RPID=0",
            10,
        ),
        (
            "https://mycouncil.surreycc.gov.uk/"
            "mgElectionResults.aspx?ID=16&RPID=0",
            16,
        ),
    ],
)
def test_supervisor_principal_election_urls_convert_to_area_indexes(
    landing_url: str,
    expected_eid: int,
) -> None:
    """Allow the three supplied landing-page links to enter indexed discovery."""

    assert principal_election_url_to_index_url(landing_url) == (
        "https://mycouncil.surreycc.gov.uk/"
        f"mgElectionElectionAreaResults.aspx?EID={expected_eid}"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/mgElectionResults.aspx?ID=16",
        "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx",
        "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=not-a-number",
        "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=5&ID=16",
    ],
)
def test_invalid_principal_election_urls_are_rejected(url: str) -> None:
    """Do not relax official host or unambiguous numeric-ID requirements."""

    with pytest.raises(ValueError):
        principal_election_url_to_index_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/mgElectionElectionAreaResults.aspx?EID=16",
        "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=16",
        "https://mycouncil.surreycc.gov.uk/mgElectionElectionAreaResults.aspx",
        "https://mycouncil.surreycc.gov.uk/mgElectionElectionAreaResults.aspx?EID=not-a-number",
    ],
)
def test_invalid_index_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        validate_index_url(url)


def test_duplicate_result_urls_are_removed() -> None:
    report = search_fallback_report(INDEX_URL, mocked_provider())

    assert len(report.areas) == 2
    assert len({area.result_url for area in report.areas}) == 2
    assert report.areas[0].result_url == (
        "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=201&RPID=0"
    )


def test_ward_names_are_extracted_from_mocked_results() -> None:
    report = search_fallback_report(INDEX_URL, mocked_provider())

    areas_by_name = {area.division_ward_name: area for area in report.areas}
    assert set(areas_by_name) == {"Addlestone", "Ash"}
    assert areas_by_name["Addlestone"].election_year == 2021
    assert areas_by_name["Addlestone"].election_name == ELECTION_NAME
    assert areas_by_name["Addlestone"].discovery_status is DiscoveryStatus.DISCOVERED


def test_search_attempts_are_recorded() -> None:
    provider = mocked_provider()
    report = search_fallback_report(INDEX_URL, provider)

    assert len(report.search_attempts) == 4
    assert report.search_attempts[0].discovery_method == "official_archive"
    assert report.search_attempts[0].status == "failed"
    assert [attempt.query for attempt in report.search_attempts[1:]] == provider.queries
    assert all(attempt.source_index_url == INDEX_URL for attempt in report.search_attempts)
    assert [attempt.status for attempt in report.search_attempts[1:]] == [
        "completed",
        "completed",
        "completed",
    ]
    assert [attempt.result_count for attempt in report.search_attempts] == [0, 1, 2, 1]


def test_url_normalisation_preserves_meaningful_parameters() -> None:
    url = (
        "http://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx"
        "?utm_campaign=test&EID=16&ID=201&XXR=0#section"
    )

    assert normalise_area_result_url(url) == (
        "https://mycouncil.surreycc.gov.uk/"
        "mgElectionAreaResults.aspx?EID=16&ID=201&XXR=0"
    )


def test_serpapi_adapter_maps_mocked_api_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "organic_results": [
            {
                "title": "Election results for Addlestone, 6 May 2021",
                "link": (
                    "https://mycouncil.surreycc.gov.uk/"
                    "mgElectionAreaResults.aspx?ID=201"
                ),
                "snippet": "Official result.",
            }
        ]
    }
    # MockTransport exercises the real httpx adapter without a network request
    # or live SerpAPI credential.
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    provider = SerpApiSearchProvider(
        api_key="test-key",
        client=httpx.Client(transport=transport),
    )
    results = provider.search("surrey election test")

    assert results == (
        SearchResult(
            title="Election results for Addlestone, 6 May 2021",
            url=(
                "https://mycouncil.surreycc.gov.uk/"
                "mgElectionAreaResults.aspx?ID=201"
            ),
            snippet="Official result.",
        ),
    )


def test_real_archive_url_discovers_id_based_result_with_matching_context() -> None:
    initial = build_search_queries(ARCHIVE_URL)
    real_name = "County Council Election 2021"
    real_date = "6 May 2021"
    context_queries = build_search_queries(ARCHIVE_URL, real_name, real_date)[len(initial):]
    area_url = (
        "https://mycouncil.surreycc.gov.uk/"
        "mgElectionAreaResults.aspx?ID=338"
    )
    provider = MockSearchProvider(
        {
            initial[0]: [
                SearchResult(
                    title="Election candidates and results by wards, 6 May 2021",
                    url=(
                        "https://mycouncil.surreycc.gov.uk/"
                        "mgElectionElectionAreaResults.aspx?Page=all&EID=16"
                    ),
                    snippet="County Council Election 2021 - Thursday, 6 May 2021.",
                )
            ],
            initial[1]: [],
            initial[2]: [],
            context_queries[0]: [
                SearchResult(
                    title="Election results for Worplesdon, 6 May 2021",
                    url=area_url,
                    snippet="County Council Election 2021 - Thursday, 6 May 2021.",
                ),
                SearchResult(
                    title="Election results for Wrong Year, 4 May 2017",
                    url=(
                        "https://mycouncil.surreycc.gov.uk/"
                        "mgElectionAreaResults.aspx?ID=999"
                    ),
                    snippet="County Council Election 2017.",
                ),
            ],
            context_queries[1]: [],
        }
    )

    report = search_fallback_report(ARCHIVE_URL, provider)

    assert report.source_index_url == ARCHIVE_URL
    assert len(report.areas) == 1
    assert report.areas[0].division_ward_name == "Worplesdon"
    assert report.areas[0].result_url == area_url
    assert report.areas[0].election_year == 2021
    assert report.areas[0].election_name == real_name
    assert sum(attempt.accepted_result_count for attempt in report.search_attempts) == 1
    assert sum(attempt.excluded_result_count for attempt in report.search_attempts) == 2
    assert all(attempt.search_date for attempt in report.search_attempts)


def test_isolated_official_id_without_target_election_context_is_rejected() -> None:
    initial = build_search_queries(ARCHIVE_URL)
    provider = MockSearchProvider(
        {
            initial[0]: [
                SearchResult(
                    title="Election candidates and results by wards, 6 May 2021",
                    url=(
                        "https://mycouncil.surreycc.gov.uk/"
                        "mgElectionElectionAreaResults.aspx?EID=16"
                    ),
                    snippet="County Council Election 2021 - Thursday, 6 May 2021.",
                )
            ],
            initial[1]: [],
            initial[2]: [
                SearchResult(
                    title="Election results for Unrelated Area",
                    url=(
                        "https://mycouncil.surreycc.gov.uk/"
                        "mgElectionAreaResults.aspx?ID=777"
                    ),
                    snippet="No election year is present.",
                )
            ],
        }
    )

    report = search_fallback_report(ARCHIVE_URL, provider)

    assert report.areas == ()


def official_archive_page() -> str:
    return """
    <html><body>
      <h1>County Council Election 2021 - Thursday, 6 May 2021</h1>
      <a href="mgElectionElectionAreaResults.aspx?EID=16&RPID=453690863">
        Election results by wards
      </a>
    </body></html>
    """


def official_archive_without_election_metadata() -> str:
    """Model an official archive that links to results but omits election labels."""
    return """
    <html><body>
      <a href="mgElectionElectionAreaResults.aspx?EID=16&RPID=453690863">
        Election results by wards
      </a>
    </body></html>
    """


def official_area_index_page() -> str:
    return """
    <html><body>
      <h1>County Council Election 2021 - Thursday, 6 May 2021</h1>
      <a href="mgElectionAreaResults.aspx?XXR=0&ID=201&RPID=999999999">Addlestone</a>
      <a href="mgElectionAreaResults.aspx?XXR=0&ID=202&RPID=453691252">Guildford South-East</a>
      <a href="mgElectionAreaResults.aspx?XXR=0&ID=201&RPID=453691252">Addlestone</a>
      <a href="https://example.com/mgElectionAreaResults.aspx?ID=999">Unrelated area</a>
      <a href="mgElectionAreaResults.aspx?ID=not-a-number">Invalid area</a>
    </body></html>
    """


def official_area_index_without_election_metadata() -> str:
    """Model a valid official area index whose visible text omits election labels."""
    return """
    <html><body>
      <h1>Election results by wards</h1>
      <a href="mgElectionAreaResults.aspx?XXR=0&ID=301&RPID=999999999">Ash</a>
    </body></html>
    """


def test_official_archive_discovers_all_published_area_links_before_search() -> None:
    client = MockOfficialArchiveClient(
        {
            ARCHIVE_URL: OfficialArchiveResponse(
                200,
                ARCHIVE_URL,
                official_archive_without_election_metadata(),
            ),
            OFFICIAL_INDEX_URL: OfficialArchiveResponse(
                200,
                OFFICIAL_INDEX_URL,
                official_area_index_page(),
            ),
        }
    )
    provider = MockSearchProvider({})

    report = discover_election_areas(ARCHIVE_URL, provider, archive_client=client)

    assert provider.queries == []
    assert [area.division_ward_name for area in report.areas] == [
        "Addlestone",
        "Guildford South-East",
    ]
    assert all(area.discovery_method == "official_archive" for area in report.areas)
    assert all(area.official_name == area.division_ward_name for area in report.areas)
    assert all(area.discovered_name == area.official_name for area in report.areas)
    assert all(area.name_status is AreaNameStatus.EXACT for area in report.areas)
    assert len({area.result_url for area in report.areas}) == 2
    assert sum(attempt.accepted_result_count for attempt in report.search_attempts) == 3
    assert any(
        attempt.rejection_reason == "duplicate_result_url"
        for attempt in report.search_attempts
    )


def test_valid_official_result_url_without_metadata_remains_discovered() -> None:
    client = MockOfficialArchiveClient(
        {
            ARCHIVE_URL: OfficialArchiveResponse(
                200,
                ARCHIVE_URL,
                official_archive_without_election_metadata(),
            ),
            OFFICIAL_INDEX_URL: OfficialArchiveResponse(
                200,
                OFFICIAL_INDEX_URL,
                official_area_index_without_election_metadata(),
            ),
        }
    )

    report = discover_election_areas(ARCHIVE_URL, MockSearchProvider({}), archive_client=client)

    assert len(report.areas) == 1
    area = report.areas[0]
    assert area.result_url.endswith("ID=301&RPID=999999999&XXR=0")
    assert area.discovery_status is DiscoveryStatus.DISCOVERED
    assert area.election_year is None
    assert area.election_name is None
    assert area.metadata_status is MetadataStatus.MISSING
    assert area.missing_metadata_fields == ("election_year", "election_name")
    accepted_attempt = next(
        attempt for attempt in report.search_attempts if attempt.discovered_url == area.result_url
    )
    assert accepted_attempt.validation_result == "accepted_metadata_missing"
    assert accepted_attempt.missing_metadata_fields == area.missing_metadata_fields


def test_valid_official_result_url_with_metadata_records_complete_metadata() -> None:
    client = MockOfficialArchiveClient(
        {
            ARCHIVE_URL: OfficialArchiveResponse(200, ARCHIVE_URL, official_archive_page()),
            OFFICIAL_INDEX_URL: OfficialArchiveResponse(
                200,
                OFFICIAL_INDEX_URL,
                official_area_index_page(),
            ),
        }
    )

    report = discover_election_areas(ARCHIVE_URL, MockSearchProvider({}), archive_client=client)

    assert all(area.discovery_status is DiscoveryStatus.DISCOVERED for area in report.areas)
    assert all(area.metadata_status is MetadataStatus.COMPLETE for area in report.areas)
    assert all(area.missing_metadata_fields == () for area in report.areas)


def test_invalid_official_result_links_are_rejected() -> None:
    report = discover_election_areas(
        ARCHIVE_URL,
        MockSearchProvider({}),
        archive_client=MockOfficialArchiveClient(
            {
                ARCHIVE_URL: OfficialArchiveResponse(200, ARCHIVE_URL, official_archive_page()),
                OFFICIAL_INDEX_URL: OfficialArchiveResponse(
                    200,
                    OFFICIAL_INDEX_URL,
                    """
                    <html><body>
                      <a href="https://example.com/mgElectionAreaResults.aspx?ID=901">Outside Surrey</a>
                      <a href="mgElectionAreaResults.aspx?ID=not-a-number">Invalid identifier</a>
                    </body></html>
                    """,
                ),
            }
        ),
    )

    assert report.areas == ()


def test_name_mismatch_is_explicit_and_does_not_silently_normalise_wards() -> None:
    status = area_name_status("Guildford South", "Guildford South-East")

    assert status is AreaNameStatus.NAME_MISMATCH


@pytest.mark.parametrize("map_index", [EAST_2026_MAP_INDEX, WEST_2026_MAP_INDEX])
def test_2026_east_and_west_map_indexes_are_accepted(map_index: str) -> None:
    """Only the two configured public 2026 map entry points are accepted."""
    from election_extractor.discovery import validate_discovery_source_url

    assert validate_discovery_source_url(map_index) == map_index


def test_2026_map_index_discovers_wards_and_deduplicates_eid_id_pairs() -> None:
    """Repeated winner links stay one ward while EID and ID remain in the URL."""
    body = """
    <html><body>
      <a href="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=352&EID=2037">Ashtead Ward</a>
      <a href="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?EID=2037&ID=352">Ashtead Ward</a>
      <a href="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=353&EID=2037">Banstead Ward</a>
    </body></html>
    """
    provider = MockSearchProvider({})
    report = discover_election_areas(
        EAST_2026_MAP_INDEX,
        provider,
        archive_client=MockOfficialArchiveClient(
            {
                EAST_2026_MAP_INDEX: OfficialArchiveResponse(
                    200, EAST_2026_MAP_INDEX, body
                )
            }
        ),
    )

    assert provider.queries == []
    assert [area.division_ward_name for area in report.areas] == [
        "Ashtead Ward",
        "Banstead Ward",
    ]
    assert [area.result_url for area in report.areas] == [
        "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?EID=2037&ID=352",
        "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?EID=2037&ID=353",
    ]
    assert all(area.discovery_method == "official_map_index" for area in report.areas)
    assert any(attempt.rejection_reason == "duplicate_result_url" for attempt in report.search_attempts)
    assert all(
        attempt.domains_searched == (
            "www10.surreycc.gov.uk",
            "mycouncil.surreycc.gov.uk",
        )
        for attempt in report.search_attempts
    )


def test_2026_map_index_rejects_invalid_or_incomplete_result_links() -> None:
    """Map discovery requires both EID and ID on an official result-page URL."""
    body = """
    <html><body>
      <a href="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=388&EID=2007">Addlestone Ward</a>
      <a href="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=389">Missing EID Ward</a>
      <a href="https://example.com/mgElectionAreaResults.aspx?ID=390&EID=2007">External Ward</a>
      <a href="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=nope&EID=2007">Invalid Ward</a>
    </body></html>
    """
    report = discover_election_areas(
        WEST_2026_MAP_INDEX,
        MockSearchProvider({}),
        archive_client=MockOfficialArchiveClient(
            {
                WEST_2026_MAP_INDEX: OfficialArchiveResponse(
                    200, WEST_2026_MAP_INDEX, body
                )
            }
        ),
    )

    assert [area.division_ward_name for area in report.areas] == ["Addlestone Ward"]
    assert report.areas[0].result_url.endswith("EID=2007&ID=388")
    assert {
        attempt.rejection_reason
        for attempt in report.search_attempts
        if attempt.validation_result == "rejected"
    } == {"invalid_map_result_url", "missing_map_result_eid_or_id"}


def test_2026_map_index_deduplicates_by_eid_and_id_not_id_alone() -> None:
    """A future map cannot collapse distinct official EID/ID result pairs."""
    body = """
    <html><body>
      <a href="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=400&EID=2007">First Ward</a>
      <a href="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=400&EID=2037">Second Ward</a>
    </body></html>
    """
    report = discover_election_areas(
        WEST_2026_MAP_INDEX,
        MockSearchProvider({}),
        archive_client=MockOfficialArchiveClient(
            {
                WEST_2026_MAP_INDEX: OfficialArchiveResponse(
                    200, WEST_2026_MAP_INDEX, body
                )
            }
        ),
    )

    assert len(report.areas) == 2
    assert {area.result_url.split("?")[1] for area in report.areas} == {
        "EID=2007&ID=400",
        "EID=2037&ID=400",
    }
