"""Provider-independent web-search interface. Only mock/none providers exist today."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, limit: int = 10) -> list[SearchResult]: ...


class NullSearchProvider:
    name = "none"

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        return []


class MockSearchProvider:
    """Returns canned results; for tests and offline development."""

    name = "mock"

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or []
        self.queries: list[str] = []

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        self.queries.append(query)
        return self.results[:limit]


def build_search(settings: Settings) -> SearchProvider:
    return MockSearchProvider() if settings.search_provider == "mock" else NullSearchProvider()
