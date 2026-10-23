from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DB, CurrentUser
from app.schemas.common import UserOut

router = APIRouter()


@router.get("/health", tags=["system"])
def health():
    """Liveness: the process is up. Does not touch the database."""
    return {"status": "ok"}


@router.get("/ready", tags=["system"])
def ready(db: DB):
    """Readiness: the database answers. (Integration status is on the admin-only /admin/integrations.)"""
    from app.core.errors import ServiceUnavailable
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise ServiceUnavailable("Database is not reachable") from exc
    return {"status": "ready"}


@router.get("/auth/me", response_model=UserOut, tags=["auth"])
def me(user: CurrentUser):
    return UserOut(id=user.id, email=user.email, display_name=user.display_name, role=user.role.value, team=user.team,
                   job_title=user.job_title, last_login_at=user.last_login_at)
