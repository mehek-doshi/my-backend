"""Agent runs, checkpoints, execution events, job executions, discovery sessions."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.enums import DiscoveryTrigger, EventLevel, JobStatus, RunStatus
from app.db.types import JSONType, UTCDateTime, enum_col, utcnow


class AgentRun(Base, UUIDPrimaryKey, Timestamps):
    """One execution of a workflow or agent. The idempotency key stops duplicate execution."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_agent_runs_idempotency_key"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_agent_runs_status_created", "status", "created_at"),
        Index("ix_agent_runs_workflow", "workflow"),
    )

    workflow: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[RunStatus] = mapped_column(enum_col(RunStatus, "run_status"), nullable=False, default=RunStatus.QUEUED)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    input: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("agent_runs.id", ondelete="SET NULL"))
    celery_task_id: Mapped[str | None] = mapped_column(String(64))
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))


class AgentCheckpoint(Base, UUIDPrimaryKey):
    __tablename__ = "agent_checkpoints"
    __table_args__ = (UniqueConstraint("run_id", "step", name="uq_agent_checkpoints_run_step"),)

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AgentEvent(Base, UUIDPrimaryKey):
    """Append-only progress log for a run (what the admin UI polls)."""

    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_agent_events_run_seq"),
        Index("ix_agent_events_run_seq", "run_id", "seq"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[EventLevel] = mapped_column(enum_col(EventLevel, "event_level"), nullable=False, default=EventLevel.INFO)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class DiscoverySession(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "discovery_sessions"
    __table_args__ = (Index("ix_discovery_sessions_created", "created_at"),)

    trigger: Mapped[DiscoveryTrigger] = mapped_column(enum_col(DiscoveryTrigger, "discovery_trigger"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(enum_col(RunStatus, "discovery_status"), nullable=False, default=RunStatus.QUEUED)
    started_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("agent_runs.id", ondelete="SET NULL"))


class JobExecution(Base, UUIDPrimaryKey):
    """Persistent record for scheduled jobs (reminders, syncs). One row per idempotency key."""

    __tablename__ = "job_executions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_job_executions_idempotency_key"),
        Index("ix_job_executions_name_started", "name", "started_at"),
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[JobStatus] = mapped_column(enum_col(JobStatus, "job_status"), nullable=False, default=JobStatus.RUNNING)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
