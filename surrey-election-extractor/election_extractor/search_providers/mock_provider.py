"""Deterministic local search provider for tests without an API key."""

from collections.abc import Mapping, Sequence

from election_extractor.models import SearchResult
from election_extractor.search_providers.base import SearchProvider


class MockSearchProvider(SearchProvider):
    """Return configured mocked results for exact query strings."""

    def __init__(self, responses: Mapping[str, Sequence[SearchResult]]) -> None:
        self._responses = {query: tuple(results) for query, results in responses.items()}
        self.queries: list[str] = []

    def search(self, query: str) -> Sequence[SearchResult]:
        self.queries.append(query)
        return self._responses.get(query, ())
