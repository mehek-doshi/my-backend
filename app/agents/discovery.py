"""Discovery agent: turns configured sources (RSS/Atom feeds) and optional web search into candidates."""
from __future__ import annotations

from urllib.parse import urlsplit

from app.agents.feeds import parse_feed
from app.agents.types import Candidate
from app.db.models import TechnologySource
from app.search.providers import SearchProvider
from app.security.ssrf import FetchError, Fetcher


class DiscoveryAgent:
    name = "discovery"

    def __init__(self, fetcher: Fetcher, search: SearchProvider | None = None, max_items: int = 20) -> None:
        self.fetcher = fetcher
        self.search = search
        self.max_items = max_items

    def crawl_source(self, source: TechnologySource) -> list[Candidate]:
        """Fetch and parse one feed. Raises FetchError / FeedParseError; the caller records the failure."""
        res = self.fetcher.get(source.url)
        if res.status_code >= 400:
            raise FetchError(f"Feed answered HTTP {res.status_code}")
        out: list[Candidate] = []
        for item in parse_feed(res.content, limit=self.max_items):
            if urlsplit(item.link).scheme not in ("http", "https"):
                continue
            out.append(Candidate(title=item.title, url=item.link, raw_summary=item.summary,
                                 published_at=item.published_at, source_id=source.id, source_name=source.name))
        return out

    def search_candidates(self, queries: list[str], limit: int = 5) -> list[Candidate]:
        if not self.search:
            return []
        out: list[Candidate] = []
        for q in queries:
            for r in self.search.search(q, limit):
                if urlsplit(r.url).scheme in ("http", "https"):
                    out.append(Candidate(title=r.title, url=r.url, raw_summary=r.snippet, source_name=f"search:{self.search.name}"))
        return out
