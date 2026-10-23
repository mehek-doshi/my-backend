"""Topics, source articles, reviews, test cases."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
                        Uuid)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.enums import ReviewDecision, TopicOrigin, TopicStatus
from app.db.types import JSONType, UTCDateTime, enum_col, utcnow


class Topic(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "topics"
    __table_args__ = (
        CheckConstraint("max_volunteers IS NULL OR max_volunteers >= 1", name="max_volunteers_positive"),
        Index("ix_topics_status_detected", "status", "detected_at"),
        Index("ix_topics_category", "category_id"),
        Index("ix_topics_fingerprint", "fingerprint"),
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("categories.id", ondelete="SET NULL"))
    status: Mapped[TopicStatus] = mapped_column(enum_col(TopicStatus, "topic_status"), nullable=False, default=TopicStatus.DISCOVERED)
    origin: Mapped[TopicOrigin] = mapped_column(enum_col(TopicOrigin, "topic_origin"), nullable=False, default=TopicOrigin.AGENT)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    suggested_use_case: Mapped[str | None] = mapped_column(Text)
    low_cost_simulation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flags: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    guardrail: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    discovery_session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("discovery_sessions.id", ondelete="SET NULL"))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="SET NULL"))
    max_volunteers: Mapped[int | None] = mapped_column(Integer)


class SourceArticle(Base, UUIDPrimaryKey):
    __tablename__ = "source_articles"
    __table_args__ = (
        UniqueConstraint("topic_id", "url_hash", name="uq_source_articles_topic_url"),
        Index("ix_source_articles_url_hash", "url_hash"),
    )

    topic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("technology_sources.id", ondelete="SET NULL"))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str | None] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class TopicReview(Base, UUIDPrimaryKey):
    """A human decision on a topic (approve, reject, merge, manual verification)."""

    __tablename__ = "topic_reviews"
    __table_args__ = (Index("ix_topic_reviews_topic_created", "topic_id", "created_at"),)

    topic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    decision: Mapped[ReviewDecision] = mapped_column(enum_col(ReviewDecision, "review_decision"), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class TopicTestCase(Base, UUIDPrimaryKey):
    """Reusable test case that an employee attaches to a topic."""

    __tablename__ = "topic_test_cases"
    __table_args__ = (Index("ix_topic_test_cases_author", "author_id"),)

    topic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
