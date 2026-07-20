"""Unit tests for candidate-level extraction from indexed search evidence."""

from election_extractor.extraction import (
    EvidenceSourceType,
    ExtractionStatus,
    build_extraction_query,
    build_extraction_queries,
    extract_candidate_results,
)
from election_extractor.official_source import (
    OfficialPageClassification,
    OfficialPageResponse,
)
from election_extractor.models import (
    DiscoveredElectionArea,
    DiscoveryStatus,
    SearchResult,
)
from election_extractor.search_providers.mock_provider import MockSearchProvider


RESULT_URL = (
    "https://mycouncil.surreycc.gov.uk/"
    "mgElectionAreaResults.aspx?ID=201&RPID=0"
)


def discovered_area() -> DiscoveredElectionArea:
    return DiscoveredElectionArea(
        election_year=2021,
        election_name="2021 Surrey County Council election",
        division_ward_name="Addlestone",
        result_url=RESULT_URL,
        source_index_url=(
            "https://mycouncil.surreycc.gov.uk/"
            "mgElectionElectionAreaResults.aspx?EID=16"
        ),
        discovery_status=DiscoveryStatus.DISCOVERED,
    )


def complete_snippet(candidate: str, party: str, votes: str, share: str, outcome: str) -> str:
    return " | ".join(
        (
            "Election date: 6 May 2021",
            "Authority: Surrey County Council",
            "Division/Ward: Addlestone",
            "Seats: 1",
            f"Candidate: {candidate}",
            f"Party: {party}",
            f"Votes: {votes}",
            f"Vote share: {share}",
            f"Outcome: {outcome}",
            "Electorate: 11,109",
            "Ballot papers issued: 2,900",
            "Ballot papers rejected: 9",
            "Turnout: 26.1%",
        )
    )


def test_extracts_one_complete_row_for_each_published_candidate() -> None:
    area = discovered_area()
    query = build_extraction_query(area)
    provider = MockSearchProvider(
        {
            query: [
                SearchResult(
                    title="Election candidate result",
                    url=RESULT_URL,
                    snippet=complete_snippet(
                        "Furey, John Raymond",
                        "Conservative",
                        "1,146",
                        "40.0%",
                        "Elected",
                    ),
                ),
                SearchResult(
                    title="Election candidate result",
                    url=RESULT_URL,
                    snippet=complete_snippet(
                        "Micklethwait, Toby",
                        "UK Independence Party",
                        "922",
                        "32.0%",
                        "Not elected",
                    ),
                ),
            ]
        }
    )

    report = extract_candidate_results([area], provider)

    assert len(report.records) == 2
    records = {record.candidate_name: record for record in report.records}
    winner = records["Furey, John Raymond"]
    assert winner.election_name == "2021 Surrey County Council election"
    assert winner.election_date == "6 May 2021"
    assert winner.authority == "Surrey County Council"
    assert winner.division_ward_name == "Addlestone"
    assert winner.number_of_seats == 1
    assert winner.original_party_name == "Conservative"
    assert winner.votes_received == 1146
    assert winner.vote_share == 40.0
    assert winner.outcome == "Elected"
    assert winner.electorate == 11109
    assert winner.ballot_papers_issued == 2900
    assert winner.ballot_papers_rejected == 9
    assert winner.turnout == 26.1
    assert winner.source_url == RESULT_URL
    assert winner.extraction_status is ExtractionStatus.COMPLETE
    assert winner.missing_fields == ()
    assert all(item.search_result_snippet for item in winner.field_evidence)
    assert all(item.extraction_timestamp for item in winner.field_evidence)


def test_preserves_original_party_name_and_deduplicates_candidate_evidence() -> None:
    area = discovered_area()
    query = build_extraction_query(area)
    result = SearchResult(
        title="Election candidate result",
        url=RESULT_URL,
        snippet=complete_snippet(
            "Micklethwait, Toby",
            "UK Independence Party",
            "922",
            "32.0%",
            "Not elected",
        ),
    )
    provider = MockSearchProvider({query: [result, result]})

    report = extract_candidate_results([area], provider)

    assert len(report.records) == 1
    assert report.records[0].original_party_name == "UK Independence Party"


def test_missing_values_remain_none_and_are_recorded() -> None:
    area = discovered_area()
    query = build_extraction_query(area)
    provider = MockSearchProvider(
        {
            query: [
                SearchResult(
                    title="Election candidate result",
                    url=RESULT_URL,
                    snippet=(
                        "Candidate: Example Candidate | Party: Independent | "
                        "Votes: N/A | Outcome: Not elected"
                    ),
                )
            ]
        }
    )

    report = extract_candidate_results([area], provider)

    record = report.records[0]
    assert record.votes_received is None
    assert record.vote_share is None
    assert record.turnout is None
    assert record.extraction_status is ExtractionStatus.INCOMPLETE
    assert "votes_received" in record.missing_fields
    assert "vote_share" in record.missing_fields
    assert "turnout" in record.missing_fields
    assert report.attempts[0].status is ExtractionStatus.INCOMPLETE


def test_unrelated_or_metadata_only_results_do_not_create_candidates() -> None:
    area = discovered_area()
    query = build_extraction_query(area)
    provider = MockSearchProvider(
        {
            query: [
                SearchResult(
                    title="Election summary",
                    url=RESULT_URL,
                    snippet="Authority: Surrey County Council | Electorate: 11,109",
                ),
                SearchResult(
                    title="Election candidate result",
                    url=(
                        "https://mycouncil.surreycc.gov.uk/"
                        "mgElectionAreaResults.aspx?ID=999"
                    ),
                    snippet="Candidate: Wrong Area | Party: Example | Votes: 1",
                ),
            ]
        }
    )

    report = extract_candidate_results([area], provider)

    assert report.records == ()
    assert report.attempts[0].status is ExtractionStatus.NO_EVIDENCE
    assert report.attempts[0].candidate_record_count == 0


def test_search_provider_query_and_attempt_are_recorded() -> None:
    area = discovered_area()
    query = build_extraction_query(area)
    provider = MockSearchProvider({query: []})

    report = extract_candidate_results([area], provider)

    assert provider.queries == list(build_extraction_queries(area))
    assert report.attempts[0].query == query
    assert report.attempts[0].source_url == RESULT_URL
    assert report.attempts[0].result_count == 0
    assert report.attempts[0].status is ExtractionStatus.NO_EVIDENCE
    assert all(attempt.search_date for attempt in report.attempts)
    assert all(
        attempt.domains_searched == ("mycouncil.surreycc.gov.uk",)
        for attempt in report.attempts
    )


def test_search_attempt_keeps_the_required_in_memory_audit_fields() -> None:
    """Record provider, time, selected URL and parsing outcome without raw JSON."""

    area = discovered_area()
    query = build_extraction_query(area)
    provider = MockSearchProvider(
        {
            query: (
                SearchResult(
                    title="Election candidate result",
                    url=RESULT_URL,
                    snippet=complete_snippet(
                        "Furey, John Raymond",
                        "Conservative",
                        "1,146",
                        "40.0%",
                        "Elected",
                    ),
                ),
            )
        }
    )

    report = extract_candidate_results(
        (area,),
        provider,
        run_targeted_searches=False,
    )
    audit = report.attempts[0]

    assert audit.search_provider == "MockSearchProvider"
    assert audit.attempt_timestamp is not None
    assert audit.attempt_timestamp.endswith("+00:00")
    assert audit.selected_urls == (RESULT_URL,)
    assert audit.parsing_warnings == ()
    assert audit.validation_warnings == ()
    assert audit.final_status is None  # Added later by the workflow validation stage.


def test_targeted_searches_stop_after_evidence_accounts_for_the_full_result() -> None:
    """Avoid extra queries only after candidates, votes, outcome and seats reconcile."""

    area = discovered_area()
    exact_query = build_extraction_query(area)
    complete_result = SearchResult(
        title="Election candidate result",
        url=RESULT_URL,
        snippet=(
            complete_snippet(
                "Furey, John Raymond",
                "Conservative",
                "1,146",
                "100%",
                "Elected",
            )
            + " | Total votes: 1,146 | Valid votes: 1,146"
        ),
    )
    provider = MockSearchProvider({exact_query: (complete_result,)})

    report = extract_candidate_results((area,), provider, run_targeted_searches=True)

    assert len(report.records) == 1
    assert provider.queries == [exact_query]
    assert len(report.attempts) == 1


def real_discovered_area() -> DiscoveredElectionArea:
    return DiscoveredElectionArea(
        election_year=2021,
        election_name="County Council Election 2021",
        division_ward_name="Worplesdon",
        result_url=(
            "https://mycouncil.surreycc.gov.uk/"
            "mgElectionAreaResults.aspx?ID=338"
        ),
        source_index_url=(
            "https://mycouncil.surreycc.gov.uk/"
            "mgElectionResults.aspx?ID=16&RPID=0"
        ),
        discovery_status=DiscoveryStatus.DISCOVERED,
    )


def test_real_comma_snippet_creates_only_supported_incomplete_candidates() -> None:
    area = real_discovered_area()
    query = build_extraction_query(area)
    provider = MockSearchProvider(
        {
            query: [
                SearchResult(
                    title="Election results for Worplesdon, 6 May 2021",
                    url=area.result_url,
                    snippet=(
                        "County Council Election 2021 - Thursday, 6 May 2021 ; "
                        "Keith Francis Witham, Conservative, 2574, 60%, Elected ; "
                        "Gina Redpath, Residents for ..."
                    ),
                )
            ]
        }
    )

    report = extract_candidate_results((area,), provider)

    records = {record.candidate_name: record for record in report.records}
    assert set(records) == {"Keith Francis Witham", "Gina Redpath"}
    assert records["Keith Francis Witham"].original_party_name == "Conservative"
    assert records["Keith Francis Witham"].votes_received == 2574
    assert records["Keith Francis Witham"].vote_share == 60.0
    assert records["Keith Francis Witham"].extraction_status is ExtractionStatus.INCOMPLETE
    assert records["Gina Redpath"].original_party_name is None
    assert records["Gina Redpath"].votes_received is None
    assert records["Gina Redpath"].extraction_status is ExtractionStatus.INCOMPLETE
    assert all(record.field_evidence for record in report.records)
    assert all(
        evidence.search_query == query
        for record in report.records
        for evidence in record.field_evidence
        if evidence.evidence_source != "Discovery metadata"
    )


def test_pipe_table_and_text_candidate_formats_are_supported() -> None:
    area = real_discovered_area()
    queries = build_extraction_queries(area)
    provider = MockSearchProvider(
        {
            queries[0]: [
                SearchResult(
                    title="Election results for Worplesdon, 6 May 2021",
                    url=area.result_url,
                    snippet=(
                        "Election Candidate | Party | Votes | % | Outcome | "
                        "Alex Morgan | Liberal Democrats | 1,234 | 31.5% | Not elected"
                    ),
                )
            ],
            queries[1]: [
                SearchResult(
                    title="Election results for Worplesdon, 6 May 2021",
                    url=area.result_url,
                    snippet="Sam Taylor Green Party 987 25% Not elected",
                )
            ],
        }
    )

    report = extract_candidate_results((area,), provider)

    records = {record.candidate_name: record for record in report.records}
    assert records["Alex Morgan"].original_party_name == "Liberal Democrats"
    assert records["Alex Morgan"].votes_received == 1234
    assert records["Alex Morgan"].vote_share == 31.5
    assert records["Sam Taylor"].original_party_name == "Green Party"
    assert records["Sam Taylor"].votes_received == 987


def test_headerless_modern_gov_candidate_row_is_recovered_conservatively() -> None:
    """Parse a real Google-style table tail only for the exact official URL."""

    area = real_discovered_area()
    query = build_extraction_query(area)
    provider = MockSearchProvider(
        {
            query: [
                SearchResult(
                    title="Election results for Worplesdon, 6 May 2021",
                    url=area.result_url,
                    snippet=(
                        "County Council Election 2021 ... Image Alex Morgan | "
                        "Liberal Democrats | 1,234 | 31.5% | Not elected"
                    ),
                ),
                # Identical-looking text from another result page is excluded
                # by the existing exact area-ID evidence gate.
                SearchResult(
                    title="Election results for Another Area, 6 May 2021",
                    url="https://mycouncil.surreycc.gov.uk/mgElectionAreaResults.aspx?ID=999",
                    snippet=(
                        "Image Wrong Person | Conservative | 9,999 | 99% | Elected"
                    ),
                ),
            ]
        }
    )

    report = extract_candidate_results((area,), provider)

    assert [record.candidate_name for record in report.records] == ["Alex Morgan"]
    record = report.records[0]
    assert record.original_party_name == "Liberal Democrats"
    assert record.votes_received == 1234
    assert record.vote_share == 31.5
    assert record.outcome == "Not elected"


def test_multiple_queries_merge_fields_and_preserve_provenance() -> None:
    area = discovered_area()
    queries = build_extraction_queries(area)
    provider = MockSearchProvider(
        {
            queries[0]: [
                SearchResult(
                    title="Election candidate result",
                    url=RESULT_URL,
                    snippet=(
                        "Election date: 6 May 2021 | Authority: Surrey County Council | "
                        "Division/Ward: Addlestone | Seats: 1 | Candidate: Jane Smith | "
                        "Party: Green Party | Electorate: 10,000 | "
                        "Ballot papers issued: 4,000 | Ballot papers rejected: 10 | "
                        "Turnout: 40.0%"
                    ),
                )
            ],
            queries[1]: [
                SearchResult(
                    title="Election candidate result",
                    url=RESULT_URL,
                    snippet=(
                        "Candidate: Jane Smith | Votes: 1,200 | "
                        "Vote share: 30.0% | Outcome: Not elected"
                    ),
                )
            ],
        }
    )

    report = extract_candidate_results((area,), provider)

    assert len(report.records) == 1
    record = report.records[0]
    assert record.votes_received == 1200
    assert record.original_party_name == "Green Party"
    assert record.extraction_status is ExtractionStatus.COMPLETE
    assert {item.search_query for item in record.field_evidence} >= {queries[0], queries[1]}


def test_conflicting_evidence_is_retained_and_never_silently_selected() -> None:
    area = real_discovered_area()
    queries = build_extraction_queries(area)
    provider = MockSearchProvider(
        {
            queries[0]: [
                SearchResult(
                    title="Election results for Worplesdon, 6 May 2021",
                    url=area.result_url,
                    snippet="Candidate: Jane Smith | Party: Conservative | Votes: 1,000",
                )
            ],
            queries[1]: [
                SearchResult(
                    title="Election results for Worplesdon, 6 May 2021",
                    url=area.result_url,
                    snippet="Candidate: Jane Smith | Party: Labour | Votes: 1,100",
                )
            ],
        }
    )

    report = extract_candidate_results((area,), provider)

    assert len(report.records) == 1
    record = report.records[0]
    assert record.original_party_name is None
    assert record.votes_received is None
    assert record.extraction_status is ExtractionStatus.INCOMPLETE
    conflicts = {conflict.field_name: conflict for conflict in record.conflicts}
    assert conflicts["original_party_name"].published_values == (
        "Conservative",
        "Labour",
    )
    assert conflicts["votes_received"].published_values == ("1,000", "1,100")
    assert len(conflicts["votes_received"].evidence) == 2


def test_extraction_audit_counts_accepted_and_excluded_results() -> None:
    area = real_discovered_area()
    query = build_extraction_query(area)
    provider = MockSearchProvider(
        {
            query: [
                SearchResult(
                    title="Election results for Worplesdon, 6 May 2021",
                    url=area.result_url,
                    snippet="Candidate: Jane Smith | Party: Independent | Votes: 100",
                ),
                SearchResult(
                    title="Election results for Another Area, 6 May 2021",
                    url=(
                        "https://mycouncil.surreycc.gov.uk/"
                        "mgElectionAreaResults.aspx?ID=999"
                    ),
                    snippet="Candidate: Wrong Person | Party: Independent | Votes: 999",
                ),
            ]
        }
    )

    report = extract_candidate_results((area,), provider)

    assert report.attempts[0].result_count == 2
    assert report.attempts[0].accepted_result_count == 1
    assert report.attempts[0].excluded_result_count == 1


class MockOfficialPageClient:
    """Return one official response or error without using live HTTP."""

    def __init__(self, response: OfficialPageResponse | Exception) -> None:
        self.response = response

    def fetch(self, url: str) -> OfficialPageResponse:
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def complete_official_page() -> str:
    return """
    <html><head><title>Election results for Worplesdon, 6 May 2021</title></head>
    <body><h1>County Council Election 2021</h1><p>Surrey County Council</p>
      <table>
        <tr><th>Election Candidate</th><th>Party</th><th>Votes</th><th>Vote Share</th><th>Outcome</th></tr>
        <tr><td>Keith Francis Witham</td><td>Conservative</td><td>2,574</td><td>60%</td><td>Elected</td></tr>
      </table>
      <table class="mgStatsTable" summary="Voting summary table">
        <caption class="mgSectionTitle">Voting Summary</caption>
        <tr><th>Details</th><th>Number</th></tr>
        <tr><td>Seats</td><td>1</td></tr><tr><td>Total votes</td><td>2,574</td></tr>
        <tr><td>Electorate</td><td>5,000</td></tr><tr><td>Number of ballot papers issued</td><td>2,580</td></tr>
        <tr><td>Number of ballot papers rejected</td><td>6</td></tr><tr><td>Turnout</td><td>51.6%</td></tr>
      </table>
    </body></html>
    """


def multi_seat_discovered_area() -> DiscoveredElectionArea:
    """Model a 2026 ward without applying its seat count to earlier elections."""
    return DiscoveredElectionArea(
        election_year=2026,
        election_name="County Council Election 2026",
        division_ward_name="Example Two-Member Ward",
        result_url=RESULT_URL,
        source_index_url=(
            "https://mycouncil.surreycc.gov.uk/"
            "mgElectionElectionAreaResults.aspx?EID=99"
        ),
        discovery_status=DiscoveryStatus.DISCOVERED,
    )


def multi_seat_official_page() -> str:
    """Reuse the official table shape with an explicitly published two-seat value."""
    return (
        complete_official_page()
        .replace("Worplesdon, 6 May 2021", "Example Two-Member Ward, 7 May 2026")
        .replace("County Council Election 2021", "County Council Election 2026")
        .replace("<td>Seats</td><td>1</td>", "<td>Seats</td><td>2</td>")
    )


def test_official_page_is_used_before_indexed_search() -> None:
    area = real_discovered_area()
    provider = MockSearchProvider({})
    client = MockOfficialPageClient(
        OfficialPageResponse(200, area.result_url, complete_official_page())
    )

    report = extract_candidate_results(
        (area,),
        provider,
        official_page_client=client,
    )

    assert provider.queries == []
    assert len(report.records) == 1
    record = report.records[0]
    assert record.candidate_name == "Keith Francis Witham"
    assert record.original_party_name == "Conservative"
    assert record.votes_received == 2574
    assert record.number_of_seats == 1
    assert record.total_votes == 2574
    assert record.electorate == 5000
    assert record.ballot_papers_issued == 2580
    assert record.ballot_papers_rejected == 6
    assert record.turnout == 51.6
    assert record.source_type is EvidenceSourceType.OFFICIAL
    assert record.extraction_status is ExtractionStatus.COMPLETE
    assert record.field_evidence
    assert all(
        item.source_type is EvidenceSourceType.OFFICIAL
        for item in record.field_evidence
        if item.evidence_source != "Discovery metadata"
    )
    assert report.attempts[0].source_type is EvidenceSourceType.OFFICIAL
    assert (
        report.official_diagnostics[0].classification
        is OfficialPageClassification.VALID_ELECTION_RESULT_PAGE
    )
    summary_evidence = {
        item.field_name: item
        for item in record.field_evidence
        if item.field_name
        in {
            "number_of_seats",
            "total_votes",
            "electorate",
            "ballot_papers_issued",
            "ballot_papers_rejected",
            "turnout",
        }
    }
    expected_summary_text = {
        "number_of_seats": "Seats: 1",
        "total_votes": "Total votes: 2,574",
        "electorate": "Electorate: 5,000",
        "ballot_papers_issued": "Number of ballot papers issued: 2,580",
        "ballot_papers_rejected": "Number of ballot papers rejected: 6",
        "turnout": "Turnout: 51.6%",
    }
    assert set(summary_evidence) == set(expected_summary_text)
    for field_name, evidence_text in expected_summary_text.items():
        field_evidence = summary_evidence[field_name]
        assert field_evidence.source_url == record.source_url
        assert field_evidence.source_type is EvidenceSourceType.OFFICIAL
        assert evidence_text in field_evidence.search_result_snippet
        assert field_evidence.extraction_timestamp is not None


def test_official_voting_summary_supports_a_published_two_seat_2026_ward() -> None:
    area = multi_seat_discovered_area()
    report = extract_candidate_results(
        (area,),
        MockSearchProvider({}),
        official_page_client=MockOfficialPageClient(
            OfficialPageResponse(200, area.result_url, multi_seat_official_page())
        ),
    )

    assert len(report.records) == 1
    assert report.records[0].number_of_seats == 2
    assert report.records[0].extraction_status is ExtractionStatus.COMPLETE


def test_missing_published_seats_remain_blank_and_keep_the_record_incomplete() -> None:
    area = real_discovered_area()
    page_without_seats = complete_official_page().replace(
        "<tr><td>Seats</td><td>1</td></tr>",
        "",
    )
    report = extract_candidate_results(
        (area,),
        MockSearchProvider({}),
        official_page_client=MockOfficialPageClient(
            OfficialPageResponse(200, area.result_url, page_without_seats)
        ),
    )

    assert len(report.records) == 1
    record = report.records[0]
    assert record.number_of_seats is None
    assert "number_of_seats" in record.missing_fields
    assert record.extraction_status is ExtractionStatus.INCOMPLETE
    assert not any(
        item.field_name == "number_of_seats" for item in record.field_evidence
    )


def test_blocked_official_page_falls_back_to_indexed_search() -> None:
    area = real_discovered_area()
    query = build_extraction_query(area)
    provider = MockSearchProvider(
        {
            query: [
                SearchResult(
                    title="Election results for Worplesdon, 6 May 2021",
                    url=area.result_url,
                    snippet="Candidate: Jane Smith | Party: Independent | Votes: 100",
                )
            ]
        }
    )
    client = MockOfficialPageClient(
        OfficialPageResponse(
            403,
            area.result_url,
            "<html><title>Access Denied</title><body>Incapsula</body></html>",
        )
    )

    report = extract_candidate_results(
        (area,),
        provider,
        official_page_client=client,
    )

    assert provider.queries == list(build_extraction_queries(area))
    assert len(report.records) == 1
    assert report.records[0].candidate_name == "Jane Smith"
    assert report.records[0].source_type is EvidenceSourceType.INDEXED_SEARCH
    assert report.records[0].votes_received == 100
    assert report.records[0].vote_share is None
    assert report.records[0].extraction_status is ExtractionStatus.INCOMPLETE
    assert (
        report.official_diagnostics[0].classification
        is OfficialPageClassification.PROTECTION_PAGE
    )


def test_unavailable_official_page_falls_back_to_indexed_search() -> None:
    area = real_discovered_area()
    query = build_extraction_query(area)
    provider = MockSearchProvider(
        {
            query: [
                SearchResult(
                    title="Election results for Worplesdon, 6 May 2021",
                    url=area.result_url,
                    snippet="Candidate: Jane Smith | Party: Independent | Votes: 100",
                )
            ]
        }
    )

    report = extract_candidate_results(
        (area,),
        provider,
        official_page_client=MockOfficialPageClient(TimeoutError("timeout")),
    )

    assert report.records[0].source_type is EvidenceSourceType.INDEXED_SEARCH
    assert report.official_diagnostics[0].classification is OfficialPageClassification.UNAVAILABLE
    assert provider.queries == list(build_extraction_queries(area))


def test_valid_official_page_does_not_invent_unpublished_candidates() -> None:
    area = real_discovered_area()
    report = extract_candidate_results(
        (area,),
        MockSearchProvider({}),
        official_page_client=MockOfficialPageClient(
            OfficialPageResponse(200, area.result_url, complete_official_page())
        ),
    )

    assert [record.candidate_name for record in report.records] == [
        "Keith Francis Witham"
    ]
