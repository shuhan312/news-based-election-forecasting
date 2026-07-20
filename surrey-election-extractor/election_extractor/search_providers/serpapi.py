"""SerpAPI adapter with bounded retries and credential-safe errors."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence

import httpx

from election_extractor.models import SearchResult
from election_extractor.search_providers.base import (
    SearchAuthenticationError,
    SearchNetworkError,
    SearchProvider,
    SearchRateLimitError,
    SearchRequestLimitError,
    SearchResponseError,
    SearchTimeoutError,
)


RetrySleep = Callable[[float], None]


class SerpApiSearchProvider(SearchProvider):
    """Query SerpAPI and return provider-neutral indexed search results.

    Temporary rate limits, server errors, timeouts and network failures use a
    small bounded exponential-backoff policy. Authentication and other client
    errors stop immediately because retrying them would waste the user's API
    allowance without changing the outcome.
    """

    _RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        api_key: str | None = None,
        *,
        endpoint: str = "https://serpapi.com/search.json",
        timeout: float = 30.0,
        result_limit: int = 100,
        max_attempts: int = 3,
        backoff_seconds: float = 1.0,
        maximum_backoff_seconds: float = 8.0,
        max_requests: int = 600,
        client: httpx.Client | None = None,
        sleep: RetrySleep = time.sleep,
    ) -> None:
        # The key remains private to this adapter and is never added to search
        # attempts, progress messages or returned SearchResult records.
        configured_key = api_key or os.getenv("SERPAPI_API_KEY")
        if not configured_key:
            raise ValueError("A SerpAPI key must be provided or set in SERPAPI_API_KEY.")
        if result_limit < 1 or result_limit > 100:
            raise ValueError("result_limit must be between 1 and 100.")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        if backoff_seconds < 0 or maximum_backoff_seconds < 0:
            raise ValueError("Backoff values must be non-negative.")
        if max_requests < 1:
            raise ValueError("max_requests must be at least 1.")

        self._api_key = configured_key
        self._endpoint = endpoint
        self._timeout = timeout
        self._result_limit = result_limit
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._maximum_backoff_seconds = maximum_backoff_seconds
        # Query retries are real API requests too. This second ceiling prevents
        # repeated transient failures from expanding a bounded query plan into
        # an unbounded number of HTTP calls.
        self._max_requests = max_requests
        self._requests_made = 0
        self._client = client or httpx.Client()
        self._sleep = sleep

    def _backoff_delay(self, failed_attempt: int, response: httpx.Response | None) -> float:
        """Return a bounded exponential delay, respecting Retry-After if present."""

        exponential = self._backoff_seconds * (2 ** (failed_attempt - 1))
        delay = min(exponential, self._maximum_backoff_seconds)
        if response is None:
            return delay

        # SerpAPI or an upstream proxy may state how long the rate limit lasts.
        # Only numeric seconds are accepted and the configured maximum remains
        # the upper bound so a response cannot pause the application indefinitely.
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = min(max(delay, float(retry_after)), self._maximum_backoff_seconds)
            except ValueError:
                pass
        return delay

    def _wait_before_retry(
        self,
        failed_attempt: int,
        response: httpx.Response | None = None,
    ) -> None:
        """Sleep only when another attempt remains."""

        if failed_attempt < self._max_attempts:
            self._sleep(self._backoff_delay(failed_attempt, response))

    @staticmethod
    def _safe_provider_error(payload: object) -> str | None:
        """Classify a provider message without returning its raw text.

        SerpAPI can attach an ``error`` string to a search whose metadata still
        says ``Success`` when Google simply found no results.  That is an empty
        query result, not a provider failure, and discovery must be allowed to
        continue with its next planned query.
        """

        if not isinstance(payload, dict) or not payload.get("error"):
            return None
        message = str(payload["error"]).casefold()
        if "api key" in message or "unauthorized" in message or "authentication" in message:
            return "authentication"
        if "rate limit" in message or "too many" in message:
            return "rate_limit"

        metadata = payload.get("search_metadata")
        search_status = (
            str(metadata.get("status", "")).casefold()
            if isinstance(metadata, dict)
            else ""
        )
        no_result_message = (
            "hasn't returned any results" in message
            or "has not returned any results" in message
            or "no results" in message
        )
        if search_status == "success" and no_result_message:
            return "empty_results"
        return "response"

    def _request(self, query: str) -> httpx.Response:
        """Run one search with limited retries for temporary failures."""

        parameters = {
            "engine": "google",
            "q": query,
            "api_key": self._api_key,
            "num": self._result_limit,
        }
        last_timeout = False
        last_network_failure = False

        for attempt in range(1, self._max_attempts + 1):
            if self._requests_made >= self._max_requests:
                raise SearchRequestLimitError(
                    "The extraction reached its indexed-search request limit."
                ) from None
            self._requests_made += 1
            try:
                response = self._client.get(
                    self._endpoint,
                    params=parameters,
                    headers={"Accept": "application/json"},
                    timeout=self._timeout,
                )
            except httpx.TimeoutException:
                # Raise a new safe exception after the last attempt. Do not
                # retain the httpx exception because it can contain the full URL.
                last_timeout = True
                last_network_failure = False
                self._wait_before_retry(attempt)
                continue
            except httpx.RequestError:
                last_network_failure = True
                last_timeout = False
                self._wait_before_retry(attempt)
                continue

            if response.status_code in {401, 403}:
                raise SearchAuthenticationError(
                    "The indexed-search API key was rejected."
                ) from None
            if response.status_code in self._RETRYABLE_STATUS_CODES:
                self._wait_before_retry(attempt, response)
                if attempt == self._max_attempts:
                    if response.status_code == 429:
                        raise SearchRateLimitError(
                            "The indexed-search rate limit was reached. Try again later."
                        ) from None
                    raise SearchResponseError(
                        "The indexed-search service is temporarily unavailable."
                    ) from None
                continue
            if response.is_error:
                raise SearchResponseError(
                    "The indexed-search service rejected the request."
                ) from None

            # SerpAPI can report provider errors inside an otherwise successful
            # HTTP 200 response. Classify those here so a rate-limit payload gets
            # the same bounded retry policy as an HTTP 429 response.
            try:
                response_payload = response.json()
            except ValueError:
                return response
            provider_error = self._safe_provider_error(response_payload)
            if provider_error == "authentication":
                raise SearchAuthenticationError(
                    "The indexed-search API key was rejected."
                ) from None
            if provider_error == "rate_limit":
                self._wait_before_retry(attempt, response)
                if attempt == self._max_attempts:
                    raise SearchRateLimitError(
                        "The indexed-search rate limit was reached. Try again later."
                    ) from None
                continue
            if provider_error == "empty_results":
                # A successful empty Google result is a valid response. Return
                # it to ``search`` so this query becomes an empty tuple and the
                # caller can continue with other discovery queries.
                return response
            if provider_error:
                raise SearchResponseError(
                    "The indexed-search service returned an error."
                ) from None
            return response

        if last_timeout:
            raise SearchTimeoutError(
                "The indexed-search request timed out. Try again later."
            ) from None
        if last_network_failure:
            raise SearchNetworkError(
                "The indexed-search service could not be reached."
            ) from None
        raise SearchResponseError("The indexed-search request failed.") from None

    def search(self, query: str) -> Sequence[SearchResult]:
        """Map a successful SerpAPI response into shared SearchResult records."""

        response = self._request(query)
        try:
            payload = response.json()
        except ValueError:
            raise SearchResponseError(
                "The indexed-search service returned invalid JSON."
            ) from None

        provider_error = self._safe_provider_error(payload)
        if provider_error == "authentication":
            raise SearchAuthenticationError(
                "The indexed-search API key was rejected."
            ) from None
        if provider_error == "rate_limit":
            raise SearchRateLimitError(
                "The indexed-search rate limit was reached. Try again later."
            ) from None
        if provider_error == "empty_results":
            return ()
        if provider_error:
            raise SearchResponseError(
                "The indexed-search service returned an error."
            ) from None

        # Only results with an explicit link can support discovery or
        # extraction; provider-specific fields stay outside the shared model.
        organic_results = payload.get("organic_results", []) if isinstance(payload, dict) else []
        return tuple(
            SearchResult(
                title=str(item.get("title", "")).strip(),
                url=str(item.get("link", "")).strip(),
                snippet=str(item.get("snippet", "")).strip(),
            )
            for item in organic_results
            if isinstance(item, dict) and item.get("link")
        )
