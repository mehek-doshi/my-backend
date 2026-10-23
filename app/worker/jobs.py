"""Background job bodies. They are plain functions (no Celery imports) so they can be tested directly and
are idempotent: `run_job_once` stores one persistent execution row per idempotency key, so a task that is
delivered twice (acks_late, retries, two beat processes) does the work once."""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.enums import (ArtifactStatus, AssignmentStatus, DiscoveryTrigger, InvitationStatus, JobStatus,
                          NotificationChannel, NotificationStatus, RunStatus, Role)
from app.db.models import (AgentRun, Artifact, Assignment, DiscoverySession, Invitation, JobExecution, Notification,
                           Topic, User)
from app.db.types import utcnow
from app.integrations.base import IntegrationError, NotConfigured
from app.integrations.registry import get_integrations
from app.services.app_settings import load_settings
from app.services.audit import audit
from app.services.notifications import notify
from app.storage.local import LocalStorage

log = logging.getLogger("techradar.jobs")
MAX_DELIVERY_ATTEMPTS = 3


class JobFailed(Exception):
    """Raised after the failure has been stored, so Celery can retry with back-off."""


def bucket(minutes: int, now=None) -> int:
    return int((now or utcnow()).timestamp() // (max(minutes, 1) * 60))


def run_job_once(db: Session, name: str, key: str, fn: Callable[[Session], dict[str, Any] | None],
                 *, lease_minutes: int | None = None) -> tuple[JobExecution, bool]:
    """Returns (execution, ran). `ran` is False when the key already succeeded or is being run by someone else."""
    lease = timedelta(minutes=lease_minutes or get_settings().job_lease_minutes)
    now = utcnow()
    row = db.scalar(select(JobExecution).where(JobExecution.idempotency_key == key))
    if row is None:
        row = JobExecution(name=name, idempotency_key=key, status=JobStatus.RUNNING, started_at=now)
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:  # another worker inserted the same key first
            return db.scalar(select(JobExecution).where(JobExecution.idempotency_key == key)), False
    else:
        if row.status in (JobStatus.SUCCEEDED, JobStatus.SKIPPED):
            return row, False
        if row.status == JobStatus.RUNNING and row.started_at > now - lease:
            return row, False  # somebody is working on it right now
        claimed = db.execute(update(JobExecution).where(JobExecution.id == row.id, JobExecution.status == row.status,
                                                        JobExecution.started_at == row.started_at)
                             .values(status=JobStatus.RUNNING, started_at=now, attempts=JobExecution.attempts + 1, error=None)).rowcount
        if not claimed:
            db.rollback()
            return db.scalar(select(JobExecution).where(JobExecution.idempotency_key == key)), False
    db.commit()
    row_id = row.id
    try:
        result = fn(db) or {}
        status, error = JobStatus.SUCCEEDED, None
    except NotConfigured as exc:
        db.rollback()
        result, status, error = {}, JobStatus.SKIPPED, str(exc)
    except Exception as exc:
        db.rollback()
        row = db.get(JobExecution, row_id)
        row.status, row.finished_at, row.error = JobStatus.FAILED, utcnow(), f"{exc.__class__.__name__}: {str(exc)[:500]}"
        db.commit()
        log.exception("Job %s failed", name)
        raise JobFailed(row.error) from exc
    row = db.get(JobExecution, row_id)
    row.status, row.finished_at, row.result, row.error = status, utcnow(), result, error
    db.commit()
    return row, True


# ---- scheduled discovery ----------------------------------------------------------------------------
def scheduled_discovery(db: Session) -> dict[str, Any]:
    from app.orchestrator.discovery import start_discovery
    from app.services.dispatch import enqueue_discovery
    interval = get_settings().discovery_interval_minutes
    session, created = start_discovery(db, DiscoveryTrigger.SCHEDULED, bucket=f"{interval}:{bucket(interval)}")
    if created:
        task_id = enqueue_discovery(session.id)
        if task_id:
            db.get(AgentRun, session.agent_run_id).celery_task_id = task_id
            db.commit()
    return {"session_id": str(session.id) if session else None, "created": created}


# ---- reminders ---------------------------------------------------------------------------------------
def send_reminders(db: Session) -> dict[str, Any]:
    rt = load_settings(db)
    now = utcnow()
    window = bucket(rt.reminder_dedupe_hours * 60, now)
    cutoff = now - timedelta(hours=rt.reminder_dedupe_hours)
    stats = {"invitations_expired": 0, "invitation_reminders": 0, "due_soon": 0, "overdue": 0}
    for inv in db.scalars(select(Invitation).where(Invitation.status == InvitationStatus.PENDING, Invitation.expires_at <= now)):
        inv.status = InvitationStatus.EXPIRED
        stats["invitations_expired"] += 1
    db.flush()
    for inv in db.scalars(select(Invitation).where(Invitation.status == InvitationStatus.PENDING, Invitation.created_at <= cutoff,
                                                   (Invitation.last_reminded_at.is_(None)) | (Invitation.last_reminded_at <= cutoff))):
        topic = db.get(Topic, inv.topic_id)
        if notify(db, inv.user_id, "invitation_reminder", f"Reminder: you are invited to '{topic.title}'",
                  f"The invitation expires {inv.expires_at:%Y-%m-%d}.", dedupe_key=f"inv-remind:{inv.id}:{window}"):
            stats["invitation_reminders"] += 1
        inv.last_reminded_at, inv.reminder_count = now, inv.reminder_count + 1
    soon = now + timedelta(hours=rt.due_soon_hours)
    for a in db.scalars(select(Assignment).where(Assignment.status == AssignmentStatus.OPEN, Assignment.due_at <= soon,
                                                 (Assignment.last_reminded_at.is_(None)) | (Assignment.last_reminded_at <= cutoff))):
        topic = db.get(Topic, a.topic_id)
        overdue = a.due_at <= now
        kind = "assignment_overdue" if overdue else "assignment_due_soon"
        title = f"Overdue: {a.stage.value} stage of '{topic.title}'" if overdue else f"Due soon: {a.stage.value} stage of '{topic.title}'"
        if notify(db, a.user_id, kind, title, f"Deadline: {a.due_at:%Y-%m-%d %H:%M} UTC", dedupe_key=f"assign-remind:{a.id}:{kind}:{window}"):
            stats["overdue" if overdue else "due_soon"] += 1
        a.last_reminded_at = now
    return stats


# ---- directory sync ---------------------------------------------------------------------------------
def sync_directory(db: Session) -> dict[str, Any]:
    s = get_settings()
    directory = get_integrations().directory
    people = directory.list_users()  # raises NotConfigured when there is none
    domains = s.allowed_email_domain_list
    existing = {u.email: u for u in db.scalars(select(User))}
    by_oid = {u.entra_object_id: u for u in existing.values() if u.entra_object_id}
    stats = {"seen": len(people), "updated": 0, "created": 0, "deactivated": 0}
    for p in people:
        u = by_oid.get(p.object_id) or existing.get(p.email)
        if u is None:
            if not s.directory_create_users or (domains and p.email.rsplit("@", 1)[-1] not in domains) or not p.enabled:
                continue
            db.add(User(email=p.email, display_name=p.display_name, entra_object_id=p.object_id, job_title=p.job_title,
                        team=p.department, role=Role.EMPLOYEE))
            stats["created"] += 1
            continue
        changed = False
        for attr, val in (("display_name", p.display_name), ("job_title", p.job_title), ("team", p.department),
                          ("entra_object_id", u.entra_object_id or p.object_id)):
            if val and getattr(u, attr) != val:
                setattr(u, attr, val)
                changed = True
        if not p.enabled and u.is_active:
            u.is_active, changed = False, True
            stats["deactivated"] += 1
            audit(db, None, "user.deactivated_by_directory", "user", u.id)
        stats["updated"] += int(changed)
    return stats


# ---- SharePoint sync --------------------------------------------------------------------------------
def sync_sharepoint(db: Session, batch: int = 20) -> dict[str, Any]:
    """Only APPROVED artifacts ever leave the system. Failures are stored on the artifact and retried next run."""
    sp = get_integrations().sharepoint
    if sp.name == "none":
        raise NotConfigured("SharePoint integration is not configured")
    folder_root = get_settings().sharepoint_folder
    rows = list(db.scalars(select(Artifact).where(Artifact.status == ArtifactStatus.APPROVED, Artifact.sharepoint_item_id.is_(None),
                                                  Artifact.storage_key.is_not(None)).order_by(Artifact.published_at).limit(batch)))
    storage = LocalStorage()
    stats = {"uploaded": 0, "failed": 0}
    for art in rows:
        topic = db.get(Topic, art.topic_id) if art.topic_id else None
        folder = f"{folder_root}/{(topic.title if topic else 'General')[:80]}".replace("\\", "/")
        folder = "/".join(p for p in (seg.strip() for seg in folder.split("/")) if p and p not in (".", ".."))
        try:
            item = sp.upload(storage.path_for(art.storage_key), folder, f"{art.id.hex[:8]}-{art.filename}")
        except NotConfigured:
            raise
        except (IntegrationError, OSError, ValueError) as exc:
            art.sync_error = f"{exc.__class__.__name__}: {str(exc)[:300]}"
            stats["failed"] += 1
            continue
        art.sharepoint_item_id, art.sharepoint_synced_at, art.sync_error = item, utcnow(), None
        stats["uploaded"] += 1
    return stats


# ---- notification delivery --------------------------------------------------------------------------
def deliver_notifications(db: Session, batch: int = 100) -> dict[str, Any]:
    integ = get_integrations()
    stats = {"sent": 0, "failed": 0, "skipped": 0}
    rows = db.execute(select(Notification, User.email).join(User, User.id == Notification.user_id)
                      .where(Notification.status == NotificationStatus.PENDING, Notification.channel != NotificationChannel.IN_APP)
                      .order_by(Notification.created_at).limit(batch)).all()
    for n, email in rows:
        try:
            if n.channel == NotificationChannel.EMAIL:
                integ.mail.send(email, n.title, n.body or n.title)
            elif n.channel == NotificationChannel.TEAMS:
                integ.teams.post(n.title, f"For {email}: {n.body}" if n.body else f"For {email}")
            elif n.channel == NotificationChannel.BUDDY:
                integ.buddy.notify(email, f"{n.title} {n.body}".strip())
            n.status, n.sent_at, n.error = NotificationStatus.SENT, utcnow(), None
            stats["sent"] += 1
        except NotConfigured as exc:
            n.status, n.error = NotificationStatus.SKIPPED, str(exc)
            stats["skipped"] += 1
        except IntegrationError as exc:
            attempts = int(n.payload.get("delivery_attempts", 0)) + 1
            n.payload = {**n.payload, "delivery_attempts": attempts}
            n.error = str(exc)[:300]
            if attempts >= MAX_DELIVERY_ATTEMPTS:
                n.status = NotificationStatus.FAILED
            stats["failed"] += 1
    return stats


# ---- reaper -----------------------------------------------------------------------------------------
def reap_stale(db: Session) -> dict[str, Any]:
    """Recover from workers that died mid-task. Every action here is safe to repeat."""
    from app.services.dispatch import enqueue_artifact_scan
    lease = timedelta(minutes=get_settings().job_lease_minutes)
    cutoff = utcnow() - lease
    stats = {"runs_failed": 0, "scans_requeued": 0, "invitations_expired": 0, "job_rows_pruned": 0}
    stats["job_rows_pruned"] = db.execute(delete(JobExecution).where(
        JobExecution.status.in_([JobStatus.SUCCEEDED, JobStatus.SKIPPED]), JobExecution.started_at < utcnow() - timedelta(days=14))).rowcount
    for run in db.scalars(select(AgentRun).where(AgentRun.status == RunStatus.RUNNING,
                                                 (AgentRun.heartbeat_at < cutoff) | (AgentRun.heartbeat_at.is_(None) & (AgentRun.started_at < cutoff)))):
        run.status, run.finished_at, run.error = RunStatus.FAILED, utcnow(), "Worker stopped responding (lease expired)"
        for s in db.scalars(select(DiscoverySession).where(DiscoverySession.agent_run_id == run.id, DiscoverySession.status == RunStatus.RUNNING)):
            s.status, s.finished_at = RunStatus.FAILED, utcnow()
        stats["runs_failed"] += 1
    stuck = list(db.scalars(select(Artifact).where(Artifact.status == ArtifactStatus.SCANNING, Artifact.updated_at < cutoff)))
    for art in stuck:
        art.status = ArtifactStatus.SUBMITTED
    for inv in db.scalars(select(Invitation).where(Invitation.status == InvitationStatus.PENDING, Invitation.expires_at <= utcnow())):
        inv.status = InvitationStatus.EXPIRED
        stats["invitations_expired"] += 1
    db.commit()
    for art in stuck:
        enqueue_artifact_scan(art.id)
        stats["scans_requeued"] += 1
    return stats
