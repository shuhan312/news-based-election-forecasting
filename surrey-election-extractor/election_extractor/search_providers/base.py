"""Provider-neutral interface for indexed election-result searches."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from election_extractor.models import SearchResult


class SearchProvider(ABC):
    """Define the single operation required by election-area discovery."""

    @abstractmethod
    def search(self, query: str) -> Sequence[SearchResult]:
        """Return indexed results for a query without assuming result order."""
        raise NotImplementedError
