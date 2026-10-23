from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.schemas.common import ORM


class CategoryOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    retired: bool


class CategoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return " ".join(v.split())


class CategoryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=2, max_length=100)
    retired: bool | None = None


class SourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=200)
    url: HttpUrl
    category_id: uuid.UUID | None = None


class SourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=2, max_length=200)
    category_id: uuid.UUID | None = None


class SourceOut(ORM):
    id: uuid.UUID
    name: str
    url: str
    kind: str
    category_id: uuid.UUID | None
    last_crawled_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    consecutive_failures: int


class ArticleOut(ORM):
    id: uuid.UUID
    url: str
    title: str
    published_at: datetime | None
    excerpt: str
    verified: bool


class TopicOut(ORM):
    """What every signed-in employee may see about a published topic."""
    id: uuid.UUID
    title: str
    summary: str
    category_id: uuid.UUID | None
    status: str
    origin: str
    suggested_use_case: str | None
    low_cost_simulation: bool
    verified: bool
    detected_at: datetime
    max_volunteers: int | None
    canonical_url: str | None


class TopicAdminOut(TopicOut):
    """Reviewer view: includes scores, flags, guardrail and verification detail."""
    flags: list[Any]
    guardrail: dict[str, Any]
    discovery_session_id: uuid.UUID | None
    requested_by: uuid.UUID | None
    reviewed_at: datetime | None
    reviewed_by: uuid.UUID | None
    rejection_reason: str | None
    merged_into_id: uuid.UUID | None


class TopicDetail(BaseModel):
    topic: TopicOut | TopicAdminOut
    articles: list[ArticleOut]


class CustomTopicIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=5, max_length=300)
    summary: str = Field(min_length=10, max_length=2000)
    source_url: HttpUrl | None = None
    category_id: uuid.UUID | None = None


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str | None = Field(None, max_length=2000)
    category_id: uuid.UUID | None = None
    max_volunteers: int | None = Field(None, ge=1, le=50)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=2000)


class MergeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_topic_id: uuid.UUID
    comment: str | None = Field(None, max_length=2000)


class VerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str = Field(min_length=3, max_length=2000)


class TestCaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=300)
    url: HttpUrl | None = None
    description: str | None = Field(None, max_length=4000)


class TestCaseOut(ORM):
    id: uuid.UUID
    topic_id: uuid.UUID
    author_id: uuid.UUID
    title: str
    url: str | None
    description: str | None
    created_at: datetime


class DiscoverySessionOut(ORM):
    id: uuid.UUID
    trigger: str
    status: str
    started_by: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    stats: dict[str, Any]
    agent_run_id: uuid.UUID | None
    created_at: datetime
