"""Tests for the bounded 2026 map-index compatibility audit."""

from __future__ import annotations

import pytest

from election_extractor.election_2026_compatibility import build_2026_compatibility_audit
from election_extractor.election_compatibility import CompatibilityPageResponse
from election_extractor.election_config import ElectionConfiguration


EAST_INDEX = "https://www10.surreycc.gov.uk/electionmap/eastSurrey/"
WEST_INDEX = "https://www10.surreycc.gov.uk/electionmap/WestSurrey/"
EAST_RESULT = "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?EID=2037&ID=352"
WEST_RESULT = "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?EID=2007&ID=388"


class MockClient:
    """Return fixed official-like pages without any network access."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def fetch(self, url: str) -> CompatibilityPageResponse:
        body = self.pages.get(url, "")
        return CompatibilityPageResponse(200 if body else 404, url, body)


def configuration(election_id: str, url: str) -> ElectionConfiguration:
    """Create one configured 2026 East/West election source."""

    return ElectionConfiguration(
        election_id=election_id,
        election_name="Surrey County Council Election 2026",
        election_year=2026,
        election_type="County Council election",
        official_url=url,
        official_url_field="official_url",
    )


def index_html(result_url: str, declared: int, party: str) -> str:
    """Model only the published map-index evidence required for the audit."""

    return f"""
    <main>
      <h1>2026 election results</h1>
      <p>{declared} of {declared} wards declared.</p>
      <h3>Map key</h3><table><caption>Map key</caption><tr><th>Key colour</th><th>Party</th></tr>
      <tr><td>colour</td><td>{party}</td></tr></table>
      <a href=\"{result_url}\">Example Ward</a>
      <a href=\"{result_url}\">Example Ward</a>
      <a href=\"https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=999\">Invalid result</a>
    </main>
    """


def result_html(authority: str) -> str:
    """Model the candidate table and official Voting Summary, not full results."""

    return f"""
    <title>Election results for Example Ward, 7 May 2026</title>
    <h1>Election results for Example Ward</h1>
    <h2>{authority} - Thursday, 7 May 2026</h2>
    <table summary=\"Example Ward - results\">
      <caption>Example Ward - results</caption>
      <tr><th>Election Candidate</th><th>Party</th><th>Votes</th><th>%</th><th>Outcome</th></tr>
      <tr><td>Candidate One</td><td>Reform UK</td><td>100</td><td>50%</td><td>Elected</td></tr>
      <tr><td>Candidate Two</td><td>Independent</td><td>90</td><td>45%</td><td>Elected</td></tr>
      <tr><td>Candidate Three</td><td>Conservative</td><td>10</td><td>5%</td><td>Not elected</td></tr>
    </table>
    <table summary=\"Voting Summary\"><caption>Voting Summary</caption>
      <tr><th>Details</th><th>Number</th></tr>
      <tr><td>Seats</td><td>2</td></tr>
      <tr><td>Total votes</td><td>200</td></tr>
      <tr><td>Electorate</td><td>500</td></tr>
      <tr><td>Number of ballot papers issued</td><td>110</td></tr>
      <tr><td>Number of ballot papers rejected</td><td>2</td></tr>
      <tr><td>Turnout</td><td>22%</td></tr>
    </table>
    """


def test_2026_audit_deduplicates_map_links_and_keeps_seats_evidence() -> None:
    """Repeated winner links are not extra wards and Seats comes from the summary."""

    client = MockClient(
        {
            EAST_INDEX: index_html(EAST_RESULT, 1, "Reform UK"),
            WEST_INDEX: index_html(WEST_RESULT, 1, "Independent"),
            EAST_RESULT: result_html("Surrey County Council"),
            WEST_RESULT: result_html("Surrey County Council"),
        }
    )
    audit = build_2026_compatibility_audit(
        (
            configuration("surrey-county-council-2026-east-surrey", EAST_INDEX),
            configuration("surrey-county-council-2026-west-surrey", WEST_INDEX),
        ),
        client,
        sample_size=1,
    )

    east = audit["east_and_west"][0]
    discovery = east["archive_and_discovery"]
    assert audit["compatibility_status"] == "compatible"
    assert discovery["raw_result_link_count"] == 3
    assert discovery["unique_result_page_count"] == 1
    assert discovery["duplicate_urls_removed"] == 1
    assert len(discovery["rejected_result_links"]) == 1
    assert discovery["output_can_be_consumed_by_extraction"] is True
    assert all(east["candidate_table_audit"]["required_fields_available_in_all_sampled_pages"].values())
    assert all(east["voting_summary_audit"]["fields_available_in_all_sampled_pages"].values())
    assert east["multi_seat_audit"]["official_seats_values_observed"] == ["2"]
    assert east["multi_seat_audit"]["multiple_elected_candidates_observed"] is True
    assert east["party_structure_audit"]["published_party_names_observed"] == [
        "Reform UK",
        "Independent",
        "Conservative",
    ]
    assert east["final_position_audit"]["official_field_present"] is False


def test_2026_audit_requires_both_configured_elections() -> None:
    """The audit cannot silently inspect one half of the 2026 election."""

    with pytest.raises(ValueError, match="requires East and West"):
        build_2026_compatibility_audit(
            (configuration("surrey-county-council-2026-east-surrey", EAST_INDEX),),
            MockClient({}),
        )
