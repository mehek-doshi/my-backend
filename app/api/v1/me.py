import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select, update

from app.api.deps import DB, CurrentUser
from app.core.errors import NotFound
from app.db.enums import NotificationChannel, Role
from app.db.models import Badge, Certificate, Notification, UserBadge
from app.db.types import utcnow
from app.schemas.common import Page, PageParams, paginate
from app.schemas.workflow import BadgeOut, CertificateOut, NotificationOut, UserBadgeOut
from app.storage.local import LocalStorage

router = APIRouter(tags=["profile"])


@router.get("/badges", response_model=list[BadgeOut])
def badge_catalog(db: DB, _: CurrentUser):
    return list(db.scalars(select(Badge).where(Badge.active.is_(True)).order_by(Badge.name)))


@router.get("/me/badges", response_model=list[UserBadgeOut])
def my_badges(db: DB, user: CurrentUser):
    rows = db.execute(select(UserBadge, Badge).join(Badge, Badge.id == UserBadge.badge_id)
                      .where(UserBadge.user_id == user.id).order_by(UserBadge.awarded_at)).all()
    return [UserBadgeOut(badge=BadgeOut.model_validate(b), awarded_at=ub.awarded_at) for ub, b in rows]


@router.get("/me/certificates", response_model=list[CertificateOut])
def my_certificates(db: DB, user: CurrentUser):
    return list(db.scalars(select(Certificate).where(Certificate.user_id == user.id).order_by(Certificate.issued_at.desc())))


@router.get("/certificates/{certificate_id}/download")
def download_certificate(certificate_id: uuid.UUID, db: DB, user: CurrentUser):
    cert = db.get(Certificate, certificate_id)
    if cert is None or (cert.user_id != user.id and user.role != Role.ADMIN):
        raise NotFound("Certificate not found")
    path = LocalStorage().path_for(cert.storage_key) if cert.storage_key else None
    if path is None or not path.is_file():
        raise NotFound("Certificate file not found")
    return FileResponse(path, media_type="application/pdf", filename=f"{cert.serial}.pdf")


@router.get("/notifications", response_model=Page[NotificationOut])
def my_notifications(db: DB, user: CurrentUser, params: PageParams = Depends(), unread: bool = False):
    stmt = select(Notification).where(Notification.user_id == user.id, Notification.channel == NotificationChannel.IN_APP)\
        .order_by(Notification.created_at.desc(), Notification.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: uuid.UUID, db: DB, user: CurrentUser):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise NotFound("Notification not found")
    if n.read_at is None:
        n.read_at = utcnow()
        db.commit()


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(db: DB, user: CurrentUser):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None)).values(read_at=utcnow()))
    db.commit()
