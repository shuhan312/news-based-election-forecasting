"""Tests for ordinary HTTP diagnostics of official Surrey result pages."""

from election_extractor.official_source import (
    OfficialPageClassification,
    OfficialPageResponse,
    fetch_and_diagnose_official_page,
    parse_official_election_page,
)


RESULT_URL = "https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=338"


class MockOfficialPageClient:
    """Return one configured response without making a network request."""

    def __init__(self, response: OfficialPageResponse | Exception) -> None:
        self.response = response
        self.urls: list[str] = []

    def fetch(self, url: str) -> OfficialPageResponse:
        self.urls.append(url)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def valid_page() -> str:
    return """
    <html><head><title>Election results for Worplesdon, 6 May 2021</title></head>
    <body>
      <h1>County Council Elections 2021</h1>
      <p>Surrey County Council</p>
      <table>
        <tr><th>Election Candidate</th><th>Party</th><th>Votes</th><th>Vote Share</th><th>Outcome</th></tr>
        <tr><td>Keith Francis Witham</td><td>Conservative</td><td>2,574</td><td>60%</td><td>Elected</td></tr>
        <tr><td>Gina Redpath</td><td>Residents for Guildford and Villages</td><td>1,716</td><td>40%</td><td>Not elected</td></tr>
      </table>
      <table class="mgStatsTable" summary="Voting summary table">
        <caption class="mgSectionTitle">Voting Summary</caption>
        <tr><th>Details</th><th>Number</th></tr>
        <tr><td>Seats</td><td>1</td></tr>
        <tr><td>Total votes</td><td>4,290</td></tr>
        <tr><td>Electorate</td><td>10,000</td></tr>
        <tr><td>Number of ballot papers issued</td><td>4,300</td></tr>
        <tr><td>Number of ballot papers rejected</td><td>10</td></tr>
        <tr><td>Turnout</td><td>43%</td></tr>
      </table>
      <table summary="Table of rejected ballot papers">
        <caption>Rejected ballot papers</caption>
        <tr><th>Description</th><th>Number</th></tr>
        <tr><td>Turnout</td><td>99%</td></tr>
      </table>
    </body></html>
    """


def test_valid_surrey_result_page_is_diagnosed() -> None:
    client = MockOfficialPageClient(OfficialPageResponse(200, RESULT_URL, valid_page()))

    result = fetch_and_diagnose_official_page(
        RESULT_URL,
        client,
        diagnostic_timestamp="2026-07-14T12:00:00+00:00",
    )

    assert result.diagnostic.classification is OfficialPageClassification.VALID_ELECTION_RESULT_PAGE
    assert result.diagnostic.status_code == 200
    assert result.diagnostic.final_url == RESULT_URL
    assert result.diagnostic.page_title == "Election results for Worplesdon, 6 May 2021"
    assert result.diagnostic.content_length > 0
    assert result.body == valid_page()


def test_block_page_is_recorded_without_bypass_attempt() -> None:
    body = "<html><title>Access Denied</title><body>Incapsula security check</body></html>"
    client = MockOfficialPageClient(OfficialPageResponse(403, RESULT_URL, body))

    result = fetch_and_diagnose_official_page(RESULT_URL, client)

    assert result.diagnostic.classification is OfficialPageClassification.PROTECTION_PAGE
    assert result.diagnostic.status_code == 403
    assert client.urls == [RESULT_URL]


def test_invalid_or_unrelated_page_is_not_treated_as_election_data() -> None:
    client = MockOfficialPageClient(
        OfficialPageResponse(200, RESULT_URL, "<html><title>Surrey homepage</title></html>")
    )

    result = fetch_and_diagnose_official_page(RESULT_URL, client)

    assert result.diagnostic.classification is OfficialPageClassification.UNRELATED_PAGE


def test_unavailable_page_records_error_type() -> None:
    client = MockOfficialPageClient(TimeoutError("timeout"))

    result = fetch_and_diagnose_official_page(RESULT_URL, client)

    assert result.diagnostic.classification is OfficialPageClassification.UNAVAILABLE
    assert result.diagnostic.status_code is None
    assert result.diagnostic.error == "TimeoutError"


def test_official_table_parser_preserves_published_values() -> None:
    data = parse_official_election_page(valid_page())
    rows = [dict(row.fields) for row in data.candidate_rows]
    shared = dict(data.shared_fields)

    assert rows == [
        {
            "candidate_name": "Keith Francis Witham",
            "original_party_name": "Conservative",
            "votes_received": "2,574",
            "vote_share": "60%",
            "outcome": "Elected",
        },
        {
            "candidate_name": "Gina Redpath",
            "original_party_name": "Residents for Guildford and Villages",
            "votes_received": "1,716",
            "vote_share": "40%",
            "outcome": "Not elected",
        },
    ]
    assert shared["number_of_seats"] == "1"
    assert shared["total_votes"] == "4,290"
    assert shared["electorate"] == "10,000"
    assert shared["ballot_papers_issued"] == "4,300"
    assert shared["ballot_papers_rejected"] == "10"
    assert shared["turnout"] == "43%"
    assert shared["election_name"] == "County Council Elections 2021"
    assert dict(data.shared_evidence)["number_of_seats"] == "Seats: 1"
    # The same label in a non-summary table is not election-summary evidence.
    assert shared["turnout"] != "99%"


def test_official_voting_summary_preserves_published_multi_seat_values() -> None:
    page = valid_page().replace("<td>Seats</td><td>1</td>", "<td>Seats</td><td>2</td>")

    data = parse_official_election_page(page)

    assert dict(data.shared_fields)["number_of_seats"] == "2"
    assert dict(data.shared_evidence)["number_of_seats"] == "Seats: 2"


def test_modern_gov_percent_header_and_same_result_redirect_are_accepted() -> None:
    redirected_url = f"{RESULT_URL}&RPID=0"
    client = MockOfficialPageClient(OfficialPageResponse(200, redirected_url, valid_page()))

    result = fetch_and_diagnose_official_page(RESULT_URL, client)
    rows = [dict(row.fields) for row in parse_official_election_page(valid_page()).candidate_rows]

    assert result.diagnostic.classification is OfficialPageClassification.VALID_ELECTION_RESULT_PAGE
    assert rows[0]["vote_share"] == "60%"
