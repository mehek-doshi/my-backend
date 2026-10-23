"""Persisting pipeline candidates as topics, and the human review actions on topics."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.types import Candidate
from app.agents.verification import VerificationAgent
from app.core.errors import Conflict, InvalidState, NotFound, Unprocessable
from app.core.textutil import canonicalize_url, clean_text, sha256_hex, title_fingerprint, url_hash
from app.db.enums import ReviewDecision, TopicOrigin, TopicStatus
from app.db.models import Category, SourceArticle, Topic, TopicReview, User
from app.db.types import utcnow
from app.security.ssrf import Fetcher
from app.services.app_settings import RuntimeSettings
from app.services.audit import audit
from app.services.lifecycle import move_topic


def add_article(db: Session, topic: Topic, cand: Candidate) -> SourceArticle | None:
    if not cand.url:
        return None
    h = url_hash(cand.url)
    existing = db.scalar(select(SourceArticle).where(SourceArticle.topic_id == topic.id, SourceArticle.url_hash == h))
    if existing:
        return existing
    art = SourceArticle(topic_id=topic.id, source_id=cand.source_id, url=cand.url[:2048], url_hash=h, title=cand.title[:500],
                        published_at=cand.published_at, excerpt=clean_text(cand.raw_summary or cand.page_text, 1000),
                        content_hash=sha256_hex(cand.page_text) if cand.page_text else None,
                        verified=bool(cand.verification.get("ok")), verification=cand.verification)
    db.add(art)
    return art


def persist_candidate(db: Session, cand: Candidate, *, origin: TopicOrigin = TopicOrigin.AGENT,
                      session_id: uuid.UUID | None = None, requested_by: uuid.UUID | None = None) -> Topic:
    """Create the topic and walk it through the lifecycle.

    A topic is published (open for volunteers) on its own only when it is verified, passed every guardrail, has a
    category and is not flagged as a possible duplicate. Everything else waits for an Admin (category, duplicate) or is
    held back (unverified, blocked)."""
    topic = Topic(
        title=clean_text(cand.title, 300), summary=cand.summary, category_id=cand.category_id, origin=origin,
        fingerprint=title_fingerprint(cand.title),
        canonical_url=canonicalize_url(cand.url) if cand.url else None, suggested_use_case=cand.suggested_use_case or None,
        low_cost_simulation=cand.low_cost, verified=cand.verified, flags=cand.flags, guardrail=cand.guardrail,
        discovery_session_id=session_id, requested_by=requested_by, status=TopicStatus.DISCOVERED)
    db.add(topic)
    db.flush()
    add_article(db, topic, cand)
    move_topic(topic, TopicStatus.ENRICHED)
    move_topic(topic, TopicStatus.CLASSIFIED)
    if cand.blocked_reasons:
        move_topic(topic, TopicStatus.BLOCKED)
    elif cand.verified:
        if cand.category_id is not None and "possible_duplicate" not in cand.flags and "needs_category" not in cand.flags:
            move_topic(topic, TopicStatus.OPEN_FOR_VOLUNTEERS)
            audit(db, None, "topic.auto_published", "topic", topic.id, {"origin": origin.value})
        else:
            move_topic(topic, TopicStatus.PENDING_REVIEW)
    else:
        move_topic(topic, TopicStatus.UNVERIFIED)
    db.flush()
    return topic


def get_topic(db: Session, topic_id: uuid.UUID) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise NotFound("Topic not found")
    return topic


def _review(db: Session, topic: Topic, reviewer: User, decision: ReviewDecision, comment: str | None,
            changes: dict[str, Any] | None = None) -> None:
    topic.reviewed_at, topic.reviewed_by = utcnow(), reviewer.id
    db.add(TopicReview(topic_id=topic.id, reviewer_id=reviewer.id, decision=decision, comment=comment, changes=changes or {}))
    audit(db, reviewer, f"topic.{decision.value}", "topic", topic.id, {"comment": comment, **(changes or {})})


def approve_topic(db: Session, topic: Topic, reviewer: User, *, comment: str | None = None, category_id: uuid.UUID | None = None,
                  max_volunteers: int | None = None) -> Topic:
    changes: dict[str, Any] = {}
    if category_id is not None:
        cat = db.get(Category, category_id)
        if cat is None or cat.retired:
            raise Unprocessable("That category does not exist or is retired")
        topic.category_id = category_id
        changes["category_id"] = str(category_id)
    if topic.category_id is None:
        raise Unprocessable("Choose a category before approving this topic")
    if max_volunteers is not None:
        topic.max_volunteers = max_volunteers
        changes["max_volunteers"] = max_volunteers
    move_topic(topic, TopicStatus.OPEN_FOR_VOLUNTEERS)  # raises if unverified / guardrail failed / wrong state
    _review(db, topic, reviewer, ReviewDecision.APPROVED, comment, changes)
    return topic


def reject_topic(db: Session, topic: Topic, reviewer: User, reason: str) -> Topic:
    move_topic(topic, TopicStatus.REJECTED)
    topic.rejection_reason = reason
    _review(db, topic, reviewer, ReviewDecision.REJECTED, reason)
    return topic


def merge_topic(db: Session, topic: Topic, target_id: uuid.UUID, reviewer: User, comment: str | None = None) -> Topic:
    if target_id == topic.id:
        raise Conflict("A topic cannot be merged into itself")
    target = get_topic(db, target_id)
    if target.status in (TopicStatus.MERGED, TopicStatus.REJECTED, TopicStatus.BLOCKED, TopicStatus.ARCHIVED):
        raise InvalidState(f"Cannot merge into a topic that is '{target.status.value}'")
    move_topic(topic, TopicStatus.MERGED)
    topic.merged_into_id = target.id
    for art in db.scalars(select(SourceArticle).where(SourceArticle.topic_id == topic.id)):
        if not db.scalar(select(SourceArticle.id).where(SourceArticle.topic_id == target.id, SourceArticle.url_hash == art.url_hash)):
            art.topic_id = target.id
    _review(db, topic, reviewer, ReviewDecision.MERGED, comment, {"merged_into": str(target.id)})
    return topic


def manually_verify(db: Session, topic: Topic, reviewer: User, comment: str | None) -> Topic:
    """A reviewer vouches for an unverified topic. Only allowed from 'unverified' and always audited."""
    if topic.status != TopicStatus.UNVERIFIED:
        raise InvalidState("Only unverified topics can be verified manually")
    topic.verified = True
    if topic.guardrail.get("passed") is not True:
        raise InvalidState("A topic that failed the guardrails cannot be verified manually")
    move_topic(topic, TopicStatus.PENDING_REVIEW)
    _review(db, topic, reviewer, ReviewDecision.VERIFIED, comment)
    return topic


def reverify(db: Session, topic: Topic, reviewer: User, fetcher: Fetcher, runtime: RuntimeSettings) -> Topic:
    ok = VerificationAgent().reverify_topic(db, topic, fetcher, runtime)
    if ok and topic.status == TopicStatus.UNVERIFIED and topic.guardrail.get("passed") is True:
        move_topic(topic, TopicStatus.PENDING_REVIEW)
    elif not ok and topic.status == TopicStatus.PENDING_REVIEW:
        move_topic(topic, TopicStatus.UNVERIFIED)
    audit(db, reviewer, "topic.reverify", "topic", topic.id, {"verified": ok})
    return topic
