from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.enums import ArtifactType, Role
from app.schemas.common import ORM


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    emails: list[str] = Field(min_length=1, max_length=100)

    @field_validator("emails")
    @classmethod
    def _norm(cls, v: list[str]) -> list[str]:
        out = []
        for e in v:
            e = e.strip().lower()
            if "@" not in e or len(e) > 320:
                raise ValueError("invalid e-mail address")
            if e not in out:
                out.append(e)
        return out


class InvitationOut(ORM):
    id: uuid.UUID
    topic_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    expires_at: datetime
    responded_at: datetime | None
    created_at: datetime


class MyInvitationOut(InvitationOut):
    topic_title: str


class VolunteerOut(ORM):
    id: uuid.UUID
    topic_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    joined_via: str
    joined_at: datetime


class VolunteerAdminOut(VolunteerOut):
    email: str
    display_name: str


class AssignmentOut(ORM):
    id: uuid.UUID
    volunteer_id: uuid.UUID
    topic_id: uuid.UUID
    stage: str
    status: str
    due_at: datetime
    started_at: datetime
    completed_at: datetime | None


class MyAssignmentOut(AssignmentOut):
    topic_title: str


class AcceptOut(BaseModel):
    invitation: InvitationOut
    volunteer: VolunteerOut


class ArtifactOut(ORM):
    id: uuid.UUID
    author_id: uuid.UUID
    topic_id: uuid.UUID | None
    assignment_id: uuid.UUID | None
    stage: str | None
    title: str
    summary: str
    type: str
    status: str
    filename: str | None
    size_bytes: int
    sha256: str | None
    repo_url: str | None
    version: int
    reviewed_at: datetime | None
    rejection_reason: str | None
    published_at: datetime | None
    created_at: datetime


class ScanSummary(BaseModel):
    blocked: bool
    findings: list[dict[str, Any]]
    antivirus: dict[str, Any]
    files_scanned: int | None = None


class ArtifactReviewOut(ArtifactOut):
    """Reviewer / author view with the automatic scan report."""
    scan_result: dict[str, Any]


class ReviewDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str | None = Field(None, max_length=2000)


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=2000)


class BadgeOut(ORM):
    id: uuid.UUID
    key: str
    name: str
    description: str
    criterion: str
    threshold: int


class UserBadgeOut(BaseModel):
    badge: BadgeOut
    awarded_at: datetime


class CertificateOut(ORM):
    id: uuid.UUID
    topic_id: uuid.UUID
    title: str
    serial: str
    issued_at: datetime


class NotificationOut(ORM):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class UserAdminOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    team: str | None
    is_active: bool
    last_login_at: datetime | None


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def _no_moderator(cls, v: Role | None) -> Role | None:
        if v == Role.MODERATOR:
            raise ValueError("The Moderator role no longer exists; use Admin")
        return v


class AuditLogOut(ORM):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_label: str
    action: str
    target_type: str
    target_id: str | None
    details: dict[str, Any]
    ip: str | None
    request_id: str | None
    created_at: datetime


class AgentRunOut(ORM):
    id: uuid.UUID
    workflow: str
    status: str
    attempts: int
    error: str | None
    input: dict[str, Any]
    output: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    created_at: datetime


class AgentEventOut(ORM):
    seq: int
    level: str
    event_type: str
    message: str
    payload: dict[str, Any]
    created_at: datetime


class JobExecutionOut(ORM):
    id: uuid.UUID
    name: str
    idempotency_key: str
    status: str
    attempts: int
    started_at: datetime
    finished_at: datetime | None
    result: dict[str, Any]
    error: str | None
