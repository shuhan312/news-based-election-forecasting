"""Tests for the application-level Surrey extraction workflow.

The tests use the local mock search provider. They therefore exercise the
workflow deterministically without a live API key, network access or changes
to the completed research datasets.
"""

from io import BytesIO

import pytest
from openpyxl import load_workbook

from election_extractor.extraction import build_extraction_query
from election_extractor.models import (
    DiscoveredElectionArea,
    DiscoveryReport,
    DiscoveryStatus,
    SearchResult,
)
from election_extractor.search_providers.mock_provider import MockSearchProvider
from election_extractor.search_providers.serpapi import SearchAuthenticationError
from election_extractor.workflow import WorkflowError, run_extraction_workflow


RESULT_URL = (
    "https://mycouncil.surreycc.gov.uk/"
    "mgElectionAreaResults.aspx?ID=201&RPID=0"
)
INDEX_URL = (
    "https://mycouncil.surreycc.gov.uk/"
    "mgElectionElectionAreaResults.aspx?EID=16"
)


def _area() -> DiscoveredElectionArea:
    """Return one known area for index-workflow orchestration tests."""

    return DiscoveredElectionArea(
        election_year=2021,
        election_name="2021 Surrey County Council election",
        division_ward_name="Addlestone",
        result_url=RESULT_URL,
        source_index_url=INDEX_URL,
        discovery_status=DiscoveryStatus.DISCOVERED,
    )


def _candidate_result() -> SearchResult:
    """Provide explicit labelled evidence accepted by the strict parser."""

    return SearchResult(
        title="Election candidate result",
        url=RESULT_URL,
        snippet=" | ".join(
            (
                "Election name: 2021 Surrey County Council election",
                "Election date: 6 May 2021",
                "Authority: Surrey County Council",
                "Division/Ward: Addlestone",
                "Seats: 1",
                "Candidate: Furey, John Raymond",
                "Party: Conservative",
                "Votes: 1,146",
                "Vote share: 40.0%",
                "Outcome: Elected",
                "Electorate: 11,109",
                "Ballot papers issued: 2,900",
                "Ballot papers rejected: 9",
                "Turnout: 26.1%",
            )
        ),
    )


def test_rejects_urls_outside_the_supported_surrey_result_pages() -> None:
    """Stop before provider access when the submitted URL is unsupported."""

    with pytest.raises(WorkflowError, match="valid Surrey election"):
        run_extraction_workflow(
            "https://example.org/results",
            provider=MockSearchProvider({}),
        )


def test_requires_an_api_key_when_no_test_provider_is_injected() -> None:
    """The real application path must not silently run without a credential."""

    with pytest.raises(WorkflowError, match="API key is required"):
        run_extraction_workflow(RESULT_URL)


def test_direct_result_url_produces_a_downloadable_auditable_workbook() -> None:
    """Join extraction, validation and workbook generation for a direct URL."""

    # Direct URLs have no trusted ward metadata before extraction, so only the
    # exact-result-URL query is permitted at this stage.
    direct_area = DiscoveredElectionArea(
        election_year=None,
        election_name=None,
        division_ward_name=None,
        result_url=RESULT_URL,
        source_index_url=RESULT_URL,
        discovery_status=DiscoveryStatus.MISSING_AREA_NAME,
    )
    exact_query = build_extraction_query(direct_area)
    provider = MockSearchProvider({exact_query: (_candidate_result(),)})
    progress = []

    result = run_extraction_workflow(
        RESULT_URL,
        provider=provider,
        progress_callback=progress.append,
    )

    assert result.source_type == "direct"
    assert result.areas_discovered == 1
    assert len(result.records) == 1
    assert len(result.voting_summaries) == 1
    assert result.extraction_attempts[0].final_status == "Incomplete"
    assert result.extraction_attempts[0].search_provider == "MockSearchProvider"
    assert result.extraction_attempts[0].selected_urls == (RESULT_URL,)
    assert result.workbook_bytes.startswith(b"PK")
    assert progress[0].stage == "validation"
    assert progress[-1].stage == "complete"

    # Inspect the generated file in memory to prove that the required
    # navigation and audit worksheets are present and readable.
    workbook = load_workbook(BytesIO(result.workbook_bytes), read_only=True)
    assert workbook.sheetnames[0] == "Index"
    assert "Addlestone" in workbook.sheetnames
    assert "Extraction Log" in workbook.sheetnames
    assert "Election Structure Metadata" not in workbook.sheetnames


def test_disabling_targeted_searches_runs_only_the_exact_url_query(monkeypatch) -> None:
    """Respect the UI checkbox without disabling the core extraction query."""

    area = _area()
    query = build_extraction_query(area)
    provider = MockSearchProvider({query: (_candidate_result(),)})

    # Isolate this test from live discovery while checking that the workflow
    # explicitly requests the supervisor-specified indexed-search path.
    def fake_discovery(index_url, search_provider, *, indexed_search_only=False):
        assert index_url == INDEX_URL
        assert search_provider.provider_name == "MockSearchProvider"
        assert indexed_search_only is True
        return DiscoveryReport(INDEX_URL, (area,), ())

    monkeypatch.setattr(
        "election_extractor.workflow.discover_election_areas",
        fake_discovery,
    )

    result = run_extraction_workflow(
        INDEX_URL,
        provider=provider,
        run_targeted_searches=False,
    )

    assert provider.queries == [query]
    assert result.areas_discovered == 1


def test_no_candidate_evidence_is_reported_as_a_failed_area() -> None:
    """Do not present an identified page with no reliable rows as complete."""

    result = run_extraction_workflow(
        RESULT_URL,
        provider=MockSearchProvider({}),
        run_targeted_searches=False,
    )

    assert result.failed == 1
    assert result.complete == 0
    assert result.incomplete == 0


def test_api_key_is_not_copied_into_outputs_or_progress() -> None:
    """Keep credentials out of workbook bytes, filenames and user messages."""

    secret = "private-test-key-123"
    direct_area = DiscoveredElectionArea(
        election_year=None,
        election_name=None,
        division_ward_name=None,
        result_url=RESULT_URL,
        source_index_url=RESULT_URL,
        discovery_status=DiscoveryStatus.MISSING_AREA_NAME,
    )
    provider = MockSearchProvider(
        {build_extraction_query(direct_area): (_candidate_result(),)}
    )
    progress = []

    result = run_extraction_workflow(
        RESULT_URL,
        api_key=secret,
        provider=provider,
        progress_callback=progress.append,
    )

    assert secret.encode() not in result.workbook_bytes
    assert secret not in result.filename
    assert all(secret not in item.message for item in progress)


def test_direct_result_provider_failure_becomes_a_safe_workflow_error() -> None:
    """Stop direct-URL processing when the provider rejects the credential."""

    class RejectedProvider(MockSearchProvider):
        def search(self, query):
            raise SearchAuthenticationError("internal-secret-provider-detail")

    with pytest.raises(WorkflowError, match="API key was rejected") as captured:
        run_extraction_workflow(
            RESULT_URL,
            provider=RejectedProvider({}),
            run_targeted_searches=False,
        )

    assert "internal-secret-provider-detail" not in str(captured.value)


def test_query_budget_stops_a_task_before_unbounded_targeted_searches(monkeypatch) -> None:
    """Apply one query ceiling across index discovery and area extraction."""

    provider = MockSearchProvider({})
    area = _area()

    def fake_discovery(index_url, search_provider, *, indexed_search_only=False):
        return DiscoveryReport(INDEX_URL, (area,), ())

    # An index area has ward/year metadata and therefore has eligible targeted
    # queries after the exact-URL search; this path can exercise the global cap.
    monkeypatch.setattr(
        "election_extractor.workflow.discover_election_areas",
        fake_discovery,
    )
    with pytest.raises(WorkflowError, match="request limit"):
        run_extraction_workflow(
            INDEX_URL,
            provider=provider,
            run_targeted_searches=True,
            max_search_queries=2,
        )

    # The wrapper blocks the third query before it reaches the real provider.
    assert len(provider.queries) == 2


def test_index_discovery_preserves_authentication_failure_category() -> None:
    """Do not turn a rejected index-search key into a no-wards message."""

    class RejectedProvider(MockSearchProvider):
        def search(self, query):
            raise SearchAuthenticationError("private-provider-detail")

    with pytest.raises(WorkflowError, match="API key was rejected") as captured:
        run_extraction_workflow(
            INDEX_URL,
            provider=RejectedProvider({}),
        )

    assert "private-provider-detail" not in str(captured.value)
