"""Article extraction agent: downloads the article page (through the SSRF-safe fetcher) and extracts text."""
from __future__ import annotations

import re

from app.agents.types import Candidate
from app.core.textutil import clean_text
from app.security.ssrf import BlockedURLError, FetchError, Fetcher

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_ACCEPT = ("text/html", "application/xhtml", "text/plain", "application/pdf")


class ArticleExtractionAgent:
    name = "extraction"

    def __init__(self, fetcher: Fetcher, max_bytes: int = 512 * 1024) -> None:
        self.fetcher = fetcher
        self.max_bytes = max_bytes

    def extract(self, cand: Candidate) -> None:
        """Fills cand.page (what happened) and cand.page_text. Never raises: a failure is data for verification."""
        if not cand.url:
            cand.page = {"ok": False, "error": "no_url"}
            return
        try:
            res = self.fetcher.get(cand.url, max_bytes=self.max_bytes, accept_types=_ACCEPT)
        except BlockedURLError as exc:
            cand.page = {"ok": False, "error": "blocked_url", "detail": str(exc)}
            return
        except FetchError as exc:
            cand.page = {"ok": False, "error": "fetch_failed", "detail": str(exc)[:200]}
            return
        ok = res.status_code < 400
        text, title = "", ""
        if ok and not res.content_type.startswith("application/pdf"):
            html = res.content.decode("utf-8", "replace")
            m = _TITLE.search(html)
            title = clean_text(m.group(1), 300) if m else ""
            text = clean_text(html, 4000)
        cand.page = {"ok": ok, "status_code": res.status_code, "content_type": res.content_type, "title": title,
                     "text_length": len(text), "final_url": res.url}
        if ok:
            cand.page_text = text
        else:
            cand.page["error"] = f"http_{res.status_code}"
