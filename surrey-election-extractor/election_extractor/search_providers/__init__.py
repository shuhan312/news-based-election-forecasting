"""Search-provider adapters used by the election discovery workflow."""

from election_extractor.search_providers.base import SearchProvider
from election_extractor.search_providers.mock_provider import MockSearchProvider
from election_extractor.search_providers.serpapi import SerpApiSearchProvider

__all__ = ["MockSearchProvider", "SearchProvider", "SerpApiSearchProvider"]
