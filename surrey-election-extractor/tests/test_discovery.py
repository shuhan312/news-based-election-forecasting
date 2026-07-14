"""Unit tests for indexed Surrey election-area discovery."""

import io
import json

import pytest

from election_extractor.discovery import build_search_queries, discover_election_areas
from election_extractor.models import DiscoveryStatus, SearchResult
from election_extractor.search_providers.mock_provider import MockSearchProvider
from election_extractor.search_providers.serpapi import SerpApiSearchProvider
from election_extractor.url_utils import normalise_area_result_url, validate_index_url


INDEX_URL = "https://mycouncil.surreycc.gov.uk/mgElectionElectionAreaResults.aspx?EID=16"
ELECTION_NAME = "2021 Surrey County Council election"


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
                ),
                SearchResult(
                    title="Ash - Election results - Surrey County Council",
                    url=(
                        "https://mycouncil.surreycc.gov.uk/"
                        "mgElectionAreaResults.aspx?ID=202&RPID=0"
                    ),
                ),
            ],
            metadata_query: [
                SearchResult(
                    title="Election results for Addlestone, 6 May 2021",
                    url=(
                        "https://mycouncil.surreycc.gov.uk/"
                        "mgElectionAreaResults.aspx?ID=201&RPID=0&gclid=tracking"
                    ),
                )
            ],
        }
    )


def test_valid_surrey_election_index_url_is_accepted() -> None:
    assert validate_index_url(INDEX_URL) == INDEX_URL


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
    report = discover_election_areas(INDEX_URL, mocked_provider())

    assert len(report.areas) == 2
    assert len({area.result_url for area in report.areas}) == 2
    assert report.areas[0].result_url == (
        "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=201&RPID=0"
    )


def test_ward_names_are_extracted_from_mocked_results() -> None:
    report = discover_election_areas(INDEX_URL, mocked_provider())

    areas_by_name = {area.division_ward_name: area for area in report.areas}
    assert set(areas_by_name) == {"Addlestone", "Ash"}
    assert areas_by_name["Addlestone"].election_year == 2021
    assert areas_by_name["Addlestone"].election_name == ELECTION_NAME
    assert areas_by_name["Addlestone"].discovery_status is DiscoveryStatus.DISCOVERED


def test_search_attempts_are_recorded() -> None:
    provider = mocked_provider()
    report = discover_election_areas(INDEX_URL, provider)

    assert len(report.search_attempts) == 3
    assert [attempt.query for attempt in report.search_attempts] == provider.queries
    assert all(attempt.source_index_url == INDEX_URL for attempt in report.search_attempts)
    assert all(attempt.status == "completed" for attempt in report.search_attempts)
    assert [attempt.result_count for attempt in report.search_attempts] == [1, 2, 1]


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
    response = io.BytesIO(json.dumps(payload).encode("utf-8"))
    monkeypatch.setattr(
        "election_extractor.search_providers.serpapi.urlopen",
        lambda request, timeout: response,
    )

    provider = SerpApiSearchProvider(api_key="test-key")
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
