"""Unit tests for candidate-level extraction from indexed search evidence."""

from election_extractor.extraction import (
    ExtractionStatus,
    build_extraction_query,
    extract_candidate_results,
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

    assert provider.queries == [query]
    assert report.attempts[0].query == query
    assert report.attempts[0].source_url == RESULT_URL
    assert report.attempts[0].result_count == 0
    assert report.attempts[0].status is ExtractionStatus.NO_EVIDENCE
