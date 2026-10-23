"""Agent-run bookkeeping: idempotent start, compare-and-set claim, append-only events, checkpoints."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.enums import EventLevel, RunStatus
from app.db.models import AgentCheckpoint, AgentEvent, AgentRun
from app.db.types import utcnow


def create_run(db: Session, workflow: str, *, idempotency_key: str | None = None, input: dict[str, Any] | None = None,
               triggered_by: uuid.UUID | None = None) -> tuple[AgentRun, bool]:
    """Returns (run, created). A repeated idempotency key returns the existing run instead of a second one."""
    if idempotency_key:
        existing = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == idempotency_key))
        if existing:
            return existing, False
    run = AgentRun(workflow=workflow, idempotency_key=idempotency_key, input=input or {}, triggered_by=triggered_by)
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:  # lost a race with another creator
        existing = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == idempotency_key))
        if existing:
            return existing, False
        raise
    return run, True


def claim_run(db: Session, run_id: uuid.UUID) -> bool:
    """queued -> running, atomically. False means somebody else already took it (duplicate execution)."""
    res = db.execute(update(AgentRun).where(AgentRun.id == run_id, AgentRun.status == RunStatus.QUEUED)
                     .values(status=RunStatus.RUNNING, started_at=utcnow(), heartbeat_at=utcnow(),
                             attempts=AgentRun.attempts + 1))
    db.commit()
    return res.rowcount == 1


def finish_run(db: Session, run: AgentRun, status: RunStatus, output: dict[str, Any] | None = None,
               error: str | None = None) -> None:
    run.status, run.finished_at, run.error = status, utcnow(), error
    if output is not None:
        run.output = output
    db.commit()


class RunRecorder:
    def __init__(self, db: Session, run: AgentRun) -> None:
        self.db, self.run = db, run
        self._seq = db.scalar(select(func.coalesce(func.max(AgentEvent.seq), 0)).where(AgentEvent.run_id == run.id)) or 0

    def event(self, event_type: str, message: str, *, level: EventLevel = EventLevel.INFO,
              payload: dict[str, Any] | None = None) -> None:
        self._seq += 1
        self.db.add(AgentEvent(run_id=self.run.id, seq=self._seq, level=level, event_type=event_type,
                               message=message[:2000], payload=payload or {}))
        self.run.heartbeat_at = utcnow()
        self.db.commit()

    def checkpoint(self, step: str, state: dict[str, Any]) -> None:
        row = self.db.scalar(select(AgentCheckpoint).where(AgentCheckpoint.run_id == self.run.id, AgentCheckpoint.step == step))
        if row:
            row.state = state
        else:
            self.db.add(AgentCheckpoint(run_id=self.run.id, step=step, state=state))
        self.db.commit()
