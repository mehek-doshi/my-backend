"""Provider wiring: one place that builds the fetcher, LLM and search provider from settings.

Tests replace `get_services` (FastAPI dependency override) or call `set_services_factory`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.core.config import Settings, get_settings
from app.llm.base import LLMProvider
from app.llm.providers import build_llm
from app.search.providers import SearchProvider, build_search
from app.security.ssrf import Fetcher, SafeFetcher


@dataclass
class Services:
    fetcher: Fetcher
    llm: LLMProvider
    search: SearchProvider


def build_services(settings: Settings | None = None) -> Services:
    s = settings or get_settings()
    fetcher = SafeFetcher(timeout=s.fetch_timeout_seconds, max_bytes=s.fetch_max_bytes,
                          max_redirects=s.fetch_max_redirects, allowed_ports=s.fetch_port_list)
    return Services(fetcher=fetcher, llm=build_llm(s), search=build_search(s))


_factory: Callable[[], Services] | None = None


def set_services_factory(factory: Callable[[], Services] | None) -> None:
    global _factory
    _factory = factory


def get_services() -> Services:
    return _factory() if _factory else build_services()
