"""Invitations, volunteers, assignments, artifacts, moderation."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.enums import (ArtifactStatus, ArtifactType, AssignmentStatus, InvitationStatus, ModerationDecision, Stage,
                          VolunteerStatus)
from app.db.types import JSONType, UTCDateTime, enum_col, utcnow


class Invitation(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "invitations"
    __table_args__ = (
        UniqueConstraint("topic_id", "user_id", name="uq_invitations_topic_user"),
        Index("ix_invitations_user_status", "user_id", "status"),
        Index("ix_invitations_status_expires", "status", "expires_at"),
    )

    topic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[InvitationStatus] = mapped_column(enum_col(InvitationStatus, "invitation_status"), nullable=False, default=InvitationStatus.PENDING)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_reminded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reminder_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Volunteer(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "volunteers"
    __table_args__ = (
        UniqueConstraint("topic_id", "user_id", name="uq_volunteers_topic_user"),
        CheckConstraint("joined_via IN ('invitation','self','admin')", name="joined_via_valid"),
        Index("ix_volunteers_topic_status", "topic_id", "status"),
        Index("ix_volunteers_user_status", "user_id", "status"),
    )

    topic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[VolunteerStatus] = mapped_column(enum_col(VolunteerStatus, "volunteer_status"), nullable=False, default=VolunteerStatus.ACTIVE)
    joined_via: Mapped[str] = mapped_column(String(20), nullable=False, default="self")
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("invitations.id", ondelete="SET NULL"))
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    left_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Assignment(Base, UUIDPrimaryKey, Timestamps):
    """One stage (Study, POC, Presentation) for one volunteer, with its deadline."""

    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint("volunteer_id", "stage", name="uq_assignments_volunteer_stage"),
        Index("ix_assignments_status_due", "status", "due_at"),
        Index("ix_assignments_user", "user_id"),
        Index("ix_assignments_topic", "topic_id"),
    )

    volunteer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("volunteers.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[Stage] = mapped_column(enum_col(Stage, "assignment_stage"), nullable=False)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    status: Mapped[AssignmentStatus] = mapped_column(enum_col(AssignmentStatus, "assignment_status"), nullable=False, default=AssignmentStatus.OPEN)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_reminded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Artifact(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_artifacts_status_created", "status", "created_at"),
        Index("ix_artifacts_author", "author_id"),
        Index("ix_artifacts_sha256", "sha256"),
        Index("ix_artifacts_topic", "topic_id"),
    )

    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="SET NULL"))
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assignments.id", ondelete="SET NULL"))
    stage: Mapped[Stage | None] = mapped_column(enum_col(Stage, "artifact_stage"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type: Mapped[ArtifactType] = mapped_column(enum_col(ArtifactType, "artifact_type"), nullable=False)
    status: Mapped[ArtifactStatus] = mapped_column(enum_col(ArtifactStatus, "artifact_status"), nullable=False, default=ArtifactStatus.SUBMITTED)
    filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))
    storage_key: Mapped[str | None] = mapped_column(String(512))
    repo_url: Mapped[str | None] = mapped_column(String(2048))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scan_result: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    sharepoint_item_id: Mapped[str | None] = mapped_column(String(200))
    sharepoint_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    sync_error: Mapped[str | None] = mapped_column(Text)


class ModerationRecord(Base, UUIDPrimaryKey):
    __tablename__ = "moderation_records"
    __table_args__ = (Index("ix_moderation_records_artifact", "artifact_id", "created_at"),)

    artifact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False)
    moderator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    decision: Mapped[ModerationDecision] = mapped_column(enum_col(ModerationDecision, "moderation_decision"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    scan_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
