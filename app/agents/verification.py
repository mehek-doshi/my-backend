"""Verification agent: is this source real, reachable and actually about the topic?

An article counts as verified only if the page was fetched through the SSRF-safe fetcher, answered
with a success status, is a readable content type and mentions the topic's key words.
A topic is verified when it has at least `min_verified_sources` verified articles.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.extraction import ArticleExtractionAgent
from app.agents.types import Candidate
from app.core.textutil import title_tokens
from app.db.models import SourceArticle, Topic
from app.security.ssrf import Fetcher
from app.services.app_settings import RuntimeSettings

_READABLE = ("text/html", "application/xhtml", "text/plain", "application/pdf")


def judge_page(page: dict, title: str, text: str) -> dict:
    reasons: list[str] = []
    if not page.get("ok"):
        reasons.append(page.get("error") or "page_not_fetched")
    elif not str(page.get("content_type", "")).startswith(_READABLE):
        reasons.append("unreadable_content_type")
    overlap = 0.0
    wanted = title_tokens(title)
    if page.get("ok") and wanted and not str(page.get("content_type", "")).startswith("application/pdf"):
        have = title_tokens(f"{page.get('title', '')} {text[:3000]}")
        overlap = len(wanted & have) / len(wanted)
        if overlap < 0.5:
            reasons.append("page_does_not_match_title")
    return {"ok": not reasons, "reasons": reasons, "title_overlap": round(overlap, 2),
            "status_code": page.get("status_code"), "content_type": page.get("content_type")}


class VerificationAgent:
    name = "verification"

    def verify_candidate(self, cand: Candidate, runtime: RuntimeSettings) -> None:
        if not cand.url:
            cand.verification = {"ok": False, "reasons": ["no_source_url"]}
            cand.verified = False
            return
        cand.verification = judge_page(cand.page, cand.title, cand.page_text or cand.raw_summary)
        cand.verified = cand.verification["ok"] and runtime.min_verified_sources <= 1

    def reverify_topic(self, db: Session, topic: Topic, fetcher: Fetcher, runtime: RuntimeSettings) -> bool:
        """Re-fetch every article of a topic and recompute `verified`."""
        extractor = ArticleExtractionAgent(fetcher)
        articles = list(db.scalars(select(SourceArticle).where(SourceArticle.topic_id == topic.id)))
        good = 0
        for art in articles:
            probe = Candidate(title=topic.title, url=art.url)
            extractor.extract(probe)
            art.verification = judge_page(probe.page, topic.title, probe.page_text)
            art.verified = art.verification["ok"]
            good += int(art.verified)
        topic.verified = good >= runtime.min_verified_sources
        return topic.verified
