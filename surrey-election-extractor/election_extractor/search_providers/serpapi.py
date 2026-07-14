"""SerpAPI adapter for live indexed-search requests."""

import json
import os
from collections.abc import Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from election_extractor.models import SearchResult
from election_extractor.search_providers.base import SearchProvider


class SerpApiSearchProvider(SearchProvider):
    """Query SerpAPI while keeping the API key outside audit records."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        endpoint: str = "https://serpapi.com/search.json",
        timeout: float = 30.0,
        result_limit: int = 100,
    ) -> None:
        # The key remains private to this adapter and is never added to discovery
        # results or search-attempt audit records.
        configured_key = api_key or os.getenv("SERPAPI_API_KEY")
        if not configured_key:
            raise ValueError("A SerpAPI key must be provided or set in SERPAPI_API_KEY.")
        if result_limit < 1 or result_limit > 100:
            raise ValueError("result_limit must be between 1 and 100.")
        self._api_key = configured_key
        self._endpoint = endpoint
        self._timeout = timeout
        self._result_limit = result_limit

    def search(self, query: str) -> Sequence[SearchResult]:
        # Convert provider-specific JSON into the provider-neutral SearchResult
        # model consumed by discovery.py.
        parameters = urlencode(
            {
                "engine": "google",
                "q": query,
                "api_key": self._api_key,
                "num": self._result_limit,
            }
        )
        request = Request(f"{self._endpoint}?{parameters}", headers={"Accept": "application/json"})
        with urlopen(request, timeout=self._timeout) as response:
            payload = json.load(response)

        return tuple(
            SearchResult(
                title=str(item.get("title", "")).strip(),
                url=str(item.get("link", "")).strip(),
                snippet=str(item.get("snippet", "")).strip(),
            )
            for item in payload.get("organic_results", [])
            if item.get("link")
        )
