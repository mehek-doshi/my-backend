"""Notifications, badges, certificates, audit logs, settings."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.enums import BadgeCriterion, NotificationChannel, NotificationStatus
from app.db.types import JSONType, UTCDateTime, enum_col, utcnow


class Notification(Base, UUIDPrimaryKey):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "channel", "dedupe_key", name="uq_notifications_user_channel_dedupe"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_status_channel", "status", "channel"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    channel: Mapped[NotificationChannel] = mapped_column(enum_col(NotificationChannel, "notification_channel"), nullable=False, default=NotificationChannel.IN_APP)
    status: Mapped[NotificationStatus] = mapped_column(enum_col(NotificationStatus, "notification_status"), nullable=False, default=NotificationStatus.SENT)
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class Badge(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "badges"
    __table_args__ = (
        UniqueConstraint("key", name="uq_badges_key"),
        CheckConstraint("threshold >= 1", name="threshold_positive"),
    )

    key: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    criterion: Mapped[BadgeCriterion] = mapped_column(enum_col(BadgeCriterion, "badge_criterion"), nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserBadge(Base, UUIDPrimaryKey):
    __tablename__ = "user_badges"
    __table_args__ = (UniqueConstraint("user_id", "badge_id", name="uq_user_badges_user_badge"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    badge_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("badges.id", ondelete="CASCADE"), nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    awarded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))


class Certificate(Base, UUIDPrimaryKey):
    __tablename__ = "certificates"
    __table_args__ = (
        UniqueConstraint("serial", name="uq_certificates_serial"),
        UniqueConstraint("user_id", "topic_id", name="uq_certificates_user_topic"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    serial: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    sha256: Mapped[str | None] = mapped_column(String(64))
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class AuditLog(Base, UUIDPrimaryKey):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_created", "created_at"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_target", "target_type", "target_id"),
        Index("ix_audit_logs_actor", "actor_id"),
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(320), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class AppSetting(Base):
    """Admin-editable runtime settings (keywords, thresholds, expiry...)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class IntegrationState(Base):
    """Cursor/state for integrations (e.g. last directory sync)."""

    __tablename__ = "integration_state"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)
