import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import DB, AdminUser, ReviewerUser
from app.core.errors import Conflict, NotFound
from app.db.enums import (ArtifactStatus, AssignmentStatus, InvitationStatus, RunStatus, TopicStatus, VolunteerStatus)
from app.db.models import (AgentEvent, AgentRun, Artifact, Assignment, AuditLog, Invitation, JobExecution, Topic, User,
                           Volunteer)
from app.db.types import utcnow
from app.schemas.common import Page, PageParams, paginate
from app.schemas.workflow import (AgentEventOut, AgentRunOut, AuditLogOut, JobExecutionOut, UserAdminOut, UserPatch)
from app.services.app_settings import RuntimeSettings, RuntimeSettingsUpdate, load_settings, update_settings
from app.services.audit import audit

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard")
def dashboard(db: DB, _: ReviewerUser):
    def count(model, *where) -> int:
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0
    now = utcnow()
    last = db.scalar(select(AgentRun).where(AgentRun.workflow == "discovery").order_by(AgentRun.created_at.desc()).limit(1))
    return {
        "topics": {s.value: count(Topic, Topic.status == s) for s in TopicStatus},
        "awaiting_topic_review": count(Topic, Topic.status == TopicStatus.PENDING_REVIEW),
        "artifacts": {s.value: count(Artifact, Artifact.status == s) for s in ArtifactStatus},
        "awaiting_artifact_review": count(Artifact, Artifact.status == ArtifactStatus.PENDING_REVIEW),
        "pending_invitations": count(Invitation, Invitation.status == InvitationStatus.PENDING),
        "active_volunteers": count(Volunteer, Volunteer.status == VolunteerStatus.ACTIVE),
        "waitlisted_volunteers": count(Volunteer, Volunteer.status == VolunteerStatus.WAITLISTED),
        "overdue_assignments": count(Assignment, Assignment.status == AssignmentStatus.OPEN, Assignment.due_at < now),
        "running_agent_runs": count(AgentRun, AgentRun.status == RunStatus.RUNNING),
        "failed_agent_runs_24h": count(AgentRun, AgentRun.status == RunStatus.FAILED, AgentRun.created_at > now - timedelta(hours=24)),
        "last_discovery": {"run_id": str(last.id), "status": last.status.value, "finished_at": last.finished_at} if last else None,
    }


@router.get("/audit-logs", response_model=Page[AuditLogOut])
def audit_logs(db: DB, _: AdminUser, params: PageParams = Depends(), action: str | None = None, actor_id: uuid.UUID | None = None,
               target_type: str | None = None, target_id: str | None = None, since: datetime | None = None):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id)
    for col, val in ((AuditLog.action, action), (AuditLog.actor_id, actor_id), (AuditLog.target_type, target_type), (AuditLog.target_id, target_id)):
        if val is not None:
            stmt = stmt.where(col == val)
    if since:
        stmt = stmt.where(AuditLog.created_at >= since)
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.get("/agent-runs", response_model=Page[AgentRunOut])
def agent_runs(db: DB, _: AdminUser, params: PageParams = Depends(), workflow: str | None = None, status: RunStatus | None = None):
    stmt = select(AgentRun).order_by(AgentRun.created_at.desc(), AgentRun.id)
    if workflow:
        stmt = stmt.where(AgentRun.workflow == workflow)
    if status:
        stmt = stmt.where(AgentRun.status == status)
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.get("/agent-runs/{run_id}", response_model=AgentRunOut)
def agent_run(run_id: uuid.UUID, db: DB, _: AdminUser):
    run = db.get(AgentRun, run_id)
    if run is None:
        raise NotFound("Run not found")
    return run


@router.get("/agent-runs/{run_id}/events", response_model=list[AgentEventOut])
def agent_run_events(run_id: uuid.UUID, db: DB, _: AdminUser, after_seq: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=500)):
    """Progress feed: poll with after_seq = the last seq you received."""
    if db.get(AgentRun, run_id) is None:
        raise NotFound("Run not found")
    return list(db.scalars(select(AgentEvent).where(AgentEvent.run_id == run_id, AgentEvent.seq > after_seq)
                           .order_by(AgentEvent.seq).limit(limit)))


@router.get("/jobs", response_model=Page[JobExecutionOut])
def job_executions(db: DB, _: AdminUser, params: PageParams = Depends(), name: str | None = None):
    stmt = select(JobExecution).order_by(JobExecution.started_at.desc(), JobExecution.id)
    if name:
        stmt = stmt.where(JobExecution.name == name)
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.get("/settings", response_model=RuntimeSettings)
def get_runtime_settings(db: DB, _: AdminUser):
    return load_settings(db)


@router.patch("/settings", response_model=RuntimeSettings)
def patch_runtime_settings(body: RuntimeSettingsUpdate, db: DB, admin: AdminUser):
    from app.core.errors import Unprocessable
    from pydantic import ValidationError
    try:
        merged, changed = update_settings(db, body, admin)
    except (ValueError, ValidationError) as exc:
        db.rollback()
        raise Unprocessable(str(exc).splitlines()[0][:300]) from exc
    audit(db, admin, "settings.update", "settings", None, {"changed": changed})
    db.commit()
    return merged


@router.get("/users", response_model=Page[UserAdminOut])
def users(db: DB, _: AdminUser, params: PageParams = Depends(), q: str | None = None):
    stmt = select(User).order_by(User.email)
    if q:
        stmt = stmt.where(User.email.like(f"%{q.strip().lower()[:100]}%"))
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def patch_user(user_id: uuid.UUID, body: UserPatch, db: DB, admin: AdminUser):
    """Roles come from Entra app roles at every sign-in; a role set here lasts until the user's next sign-in.
    Deactivating a user is permanent until an admin re-activates them."""
    u = db.get(User, user_id)
    if u is None:
        raise NotFound("User not found")
    if u.id == admin.id:
        raise Conflict("You cannot change your own role or access")
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "role" in changes:
        u.role = changes["role"]
    if "is_active" in changes:
        u.is_active = changes["is_active"]
    audit(db, admin, "user.update", "user", u.id, {k: getattr(v, "value", v) for k, v in changes.items()})
    db.commit()
    return u


@router.get("/integrations")
def integrations(_: AdminUser):
    """Which integrations are configured. 'verified_against_live_system' is always false: this code has only been
    exercised against mocked transports."""
    from app.integrations.registry import get_integrations
    return get_integrations().status()
