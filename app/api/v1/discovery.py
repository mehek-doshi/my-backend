import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DB, AdminUser
from app.core.errors import NotFound
from app.db.enums import DiscoveryTrigger
from app.db.models import AgentRun, DiscoverySession
from app.schemas.common import Page, PageParams, paginate
from app.schemas.topics import DiscoverySessionOut
from app.orchestrator.discovery import start_discovery
from app.services.dispatch import enqueue_discovery

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.post("/sessions", response_model=DiscoverySessionOut, status_code=202)
def start(db: DB, admin: AdminUser):
    """Queue a discovery run. The work happens in a Celery worker; poll the session or its run events."""
    session, created = start_discovery(db, DiscoveryTrigger.MANUAL, user=admin)
    if created:
        task_id = enqueue_discovery(session.id)
        if task_id:
            run = db.get(AgentRun, session.agent_run_id)
            run.celery_task_id = task_id
            db.commit()
        db.refresh(session)
    return session


@router.get("/sessions", response_model=Page[DiscoverySessionOut])
def list_sessions(db: DB, _: AdminUser, params: PageParams = Depends()):
    rows, total = paginate(db, select(DiscoverySession).order_by(DiscoverySession.created_at.desc(), DiscoverySession.id), params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.get("/sessions/{session_id}", response_model=DiscoverySessionOut)
def get_session(session_id: uuid.UUID, db: DB, _: AdminUser):
    s = db.get(DiscoverySession, session_id)
    if s is None:
        raise NotFound("Discovery session not found")
    return s
