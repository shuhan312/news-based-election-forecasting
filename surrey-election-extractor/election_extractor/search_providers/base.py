"""Provider-neutral interface for indexed election-result searches."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from election_extractor.models import SearchResult


class SearchProviderError(RuntimeError):
    """Base class for credential-safe provider failures."""


class SearchAuthenticationError(SearchProviderError):
    """The provider rejected the submitted credential."""


class SearchRateLimitError(SearchProviderError):
    """The provider remained rate limited after the allowed retries."""


class SearchTimeoutError(SearchProviderError):
    """The provider timed out after the allowed retries."""


class SearchNetworkError(SearchProviderError):
    """The provider remained unreachable after the allowed retries."""


class SearchResponseError(SearchProviderError):
    """The provider returned an unusable or non-retryable response."""


class SearchRequestLimitError(SearchProviderError):
    """The configured query or HTTP-request budget was exhausted."""


class SearchProvider(ABC):
    """Define the single operation required by election-area discovery."""

    @property
    def provider_name(self) -> str:
        """Return a safe adapter name for audit records."""

        return type(self).__name__

    @abstractmethod
    def search(self, query: str) -> Sequence[SearchResult]:
        """Return indexed results for a query without assuming result order."""
        raise NotImplementedError


class BudgetedSearchProvider(SearchProvider):
    """Apply one provider-neutral query budget across discovery and extraction."""

    def __init__(self, provider: SearchProvider, max_queries: int) -> None:
        if max_queries < 1:
            raise ValueError("max_queries must be at least 1.")
        self._provider = provider
        self._max_queries = max_queries
        self._queries_used = 0

    @property
    def queries_used(self) -> int:
        """Return the number of searches charged to this workflow."""

        return self._queries_used

    @property
    def provider_name(self) -> str:
        """Keep the audit focused on the real provider, not this wrapper."""

        return self._provider.provider_name

    def search(self, query: str) -> Sequence[SearchResult]:
        """Reject work beyond the budget before calling the real provider."""

        if self._queries_used >= self._max_queries:
            raise SearchRequestLimitError(
                "The extraction reached its indexed-search query limit."
            )
        self._queries_used += 1
        return self._provider.search(query)
