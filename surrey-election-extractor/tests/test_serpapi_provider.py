"""Tests for bounded retries and safe SerpAPI failure handling."""

import httpx
import pytest

from election_extractor.search_providers.serpapi import (
    SearchAuthenticationError,
    SearchNetworkError,
    SearchRateLimitError,
    SearchResponseError,
    SearchTimeoutError,
    SerpApiSearchProvider,
)
from election_extractor.search_providers.base import SearchRequestLimitError


SECRET = "credential-that-must-not-appear"


def _provider(handler, *, attempts=3, sleep=None, **options) -> SerpApiSearchProvider:
    """Build an adapter around a local httpx transport for deterministic tests."""

    return SerpApiSearchProvider(
        api_key=SECRET,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_attempts=attempts,
        backoff_seconds=0.5,
        maximum_backoff_seconds=2.0,
        sleep=sleep or (lambda seconds: None),
        **options,
    )


def test_rate_limit_retries_with_bounded_exponential_backoff() -> None:
    """Retry 429 responses, honour Retry-After and stop after three attempts."""

    calls = 0
    delays = []

    def handler(request):
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(429, headers={"Retry-After": "1.5"})
        return httpx.Response(200, json={"organic_results": []})

    results = _provider(handler, sleep=delays.append).search("surrey election")

    assert results == ()
    assert calls == 3
    assert delays == [1.5, 1.5]


def test_persistent_rate_limit_stops_at_the_configured_attempt_limit() -> None:
    """Never continue retrying indefinitely when the provider remains limited."""

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(429)

    with pytest.raises(SearchRateLimitError) as captured:
        _provider(handler).search("surrey election")

    assert calls == 3
    assert SECRET not in str(captured.value)


def test_rate_limit_inside_successful_http_payload_is_also_retried() -> None:
    """Apply the retry policy when SerpAPI reports limits inside HTTP 200 JSON."""

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(200, json={"error": "Rate limit reached"})
        return httpx.Response(200, json={"organic_results": []})

    assert _provider(handler).search("surrey election") == ()
    assert calls == 3


def test_rejected_key_fails_immediately_without_retrying() -> None:
    """A second request cannot repair an invalid credential and wastes quota."""

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": "Invalid API key"})

    with pytest.raises(SearchAuthenticationError) as captured:
        _provider(handler).search("surrey election")

    assert calls == 1
    assert SECRET not in str(captured.value)


@pytest.mark.parametrize(
    ("exception_factory", "expected_error"),
    (
        (
            lambda request: httpx.ReadTimeout("temporary timeout", request=request),
            SearchTimeoutError,
        ),
        (
            lambda request: httpx.ConnectError("temporary network failure", request=request),
            SearchNetworkError,
        ),
    ),
)
def test_temporary_request_failures_retry_then_return_safe_error(
    exception_factory,
    expected_error,
) -> None:
    """Classify exhausted timeout and network retries without leaking the URL."""

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise exception_factory(request)

    with pytest.raises(expected_error) as captured:
        _provider(handler).search("surrey election")

    assert calls == 3
    assert SECRET not in str(captured.value)


def test_invalid_json_and_provider_error_payloads_are_not_silently_accepted() -> None:
    """Do not turn malformed or explicit error responses into empty success."""

    invalid_json = _provider(lambda request: httpx.Response(200, content=b"not-json"))
    with pytest.raises(SearchResponseError):
        invalid_json.search("surrey election")

    rejected_payload = _provider(
        lambda request: httpx.Response(200, json={"error": "Invalid API key supplied"})
    )
    with pytest.raises(SearchAuthenticationError):
        rejected_payload.search("surrey election")


def test_successful_google_search_with_no_results_returns_an_empty_sequence() -> None:
    """Let discovery continue when one valid SerpAPI query has no matches."""

    provider = _provider(
        lambda request: httpx.Response(
            200,
            json={
                "search_metadata": {"status": "Success"},
                "search_information": {"organic_results_state": "Fully empty"},
                "error": "Google hasn't returned any results for this query.",
            },
        )
    )

    # Empty results are evidence about this query, not a reason to abort all
    # remaining landing-page and area-index searches.
    assert provider.search("site:mycouncil.surreycc.gov.uk election") == ()


def test_failed_search_metadata_is_still_a_provider_error() -> None:
    """Do not mistake a genuine SerpAPI processing failure for an empty search."""

    provider = _provider(
        lambda request: httpx.Response(
            200,
            json={
                "search_metadata": {"status": "Error"},
                "error": "We couldn't get valid results for this search.",
            },
        )
    )

    with pytest.raises(SearchResponseError):
        provider.search("surrey election")


def test_constructor_rejects_unbounded_or_invalid_retry_settings() -> None:
    """Fail configuration early instead of creating an unsafe retry policy."""

    with pytest.raises(ValueError, match="max_attempts"):
        SerpApiSearchProvider(api_key=SECRET, max_attempts=0)
    with pytest.raises(ValueError, match="Backoff"):
        SerpApiSearchProvider(api_key=SECRET, backoff_seconds=-1)
    with pytest.raises(ValueError, match="max_requests"):
        SerpApiSearchProvider(api_key=SECRET, max_requests=0)
    with pytest.raises(ValueError, match="max_pages"):
        SerpApiSearchProvider(api_key=SECRET, max_pages=0)


def test_search_follows_explicit_pagination_and_deduplicates_results() -> None:
    """Recover later indexed wards without accepting duplicate result rows."""

    requested_starts = []

    def handler(request):
        start = int(request.url.params.get("start", "0"))
        requested_starts.append(start)
        if start == 0:
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {"title": "Area A", "link": "https://example.test/a", "snippet": "A"}
                    ],
                    "serpapi_pagination": {
                        "next": "https://serpapi.com/search.json?q=x&start=10"
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    # The repeated first-page row must not inflate discovery.
                    {"title": "Area A", "link": "https://example.test/a", "snippet": "A"},
                    {"title": "Area B", "link": "https://example.test/b", "snippet": "B"},
                ]
            },
        )

    results = _provider(handler).search(
        "site:mycouncil.surreycc.gov.uk inurl:mgElectionAreaResults.aspx 2017"
    )

    assert requested_starts == [0, 10]
    assert [result.title for result in results] == ["Area A", "Area B"]


def test_search_stops_at_the_configured_page_limit() -> None:
    """Keep broad discovery searches within a declared API-cost boundary."""

    requested_starts = []

    def handler(request):
        start = int(request.url.params.get("start", "0"))
        requested_starts.append(start)
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {
                        "title": f"Area {start}",
                        "link": f"https://example.test/{start}",
                        "snippet": "result",
                    }
                ],
                "serpapi_pagination": {
                    "next": f"https://serpapi.com/search.json?q=x&start={start + 10}"
                },
            },
        )

    results = _provider(handler, max_pages=2).search(
        "site:mycouncil.surreycc.gov.uk inurl:mgElectionAreaResults.aspx 2017"
    )

    assert requested_starts == [0, 10]
    assert len(results) == 2


def test_narrow_extraction_query_does_not_spend_quota_on_later_pages() -> None:
    """Reserve pagination for area discovery rather than every field search."""

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {"title": "Candidate", "link": "https://example.test/a"}
                ],
                "serpapi_pagination": {
                    "next": "https://serpapi.com/search.json?q=x&start=10"
                },
            },
        )

    results = _provider(handler).search('"Oxted" candidates votes "2017"')

    assert calls == 1
    assert len(results) == 1


def test_http_request_ceiling_also_counts_retry_attempts() -> None:
    """Prevent retries from bypassing the complete-task HTTP request ceiling."""

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    provider = SerpApiSearchProvider(
        api_key=SECRET,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_attempts=3,
        max_requests=2,
        sleep=lambda seconds: None,
    )

    with pytest.raises(SearchRequestLimitError):
        provider.search("surrey election")
    assert calls == 2
