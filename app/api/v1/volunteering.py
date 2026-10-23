import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import DB, AdminUser, CurrentUser
from app.core.errors import NotFound, Unprocessable
from app.db.enums import AssignmentStatus, InvitationStatus, Role, TopicStatus
from app.db.models import Assignment, Invitation, Topic, User, Volunteer
from app.schemas.common import Page, PageParams, paginate
from app.schemas.workflow import (AcceptOut, AssignmentOut, InvitationOut, InviteIn, MyAssignmentOut, MyInvitationOut,
                                  VolunteerAdminOut, VolunteerOut)
from app.services import volunteering as svc

router = APIRouter(tags=["volunteering"])


def _open_topic_for(user: User, topic: Topic | None) -> Topic:
    if topic is None or (user.role != Role.ADMIN and topic.status not in svc.OPEN_STATUSES):
        raise NotFound("Topic not found")
    return topic


# ---- invitations ------------------------------------------------------------------------------------
@router.post("/topics/{topic_id}/invitations", response_model=list[InvitationOut], status_code=201)
def invite(topic_id: uuid.UUID, body: InviteIn, db: DB, admin: AdminUser):
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise NotFound("Topic not found")
    users = list(db.scalars(select(User).where(User.email.in_(body.emails))))
    missing = sorted(set(body.emails) - {u.email for u in users})
    if missing and not users:
        raise Unprocessable("None of those people have signed in to Tech Radar yet", details={"unknown": missing})
    created = svc.invite_users(db, admin, topic, users)
    db.commit()
    return created


@router.get("/topics/{topic_id}/invitations", response_model=Page[InvitationOut])
def topic_invitations(topic_id: uuid.UUID, db: DB, _: AdminUser, params: PageParams = Depends()):
    rows, total = paginate(db, select(Invitation).where(Invitation.topic_id == topic_id).order_by(Invitation.created_at.desc(), Invitation.id), params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.get("/invitations/mine", response_model=list[MyInvitationOut])
def my_invitations(db: DB, user: CurrentUser, status: InvitationStatus | None = InvitationStatus.PENDING):
    stmt = select(Invitation, Topic.title).join(Topic, Topic.id == Invitation.topic_id).where(Invitation.user_id == user.id)\
        .order_by(Invitation.created_at.desc())
    if status:
        stmt = stmt.where(Invitation.status == status)
    out = []
    for inv, title in db.execute(stmt).all():
        d = InvitationOut.model_validate(inv).model_dump()
        out.append(MyInvitationOut(**d, topic_title=title))
    return out


@router.post("/invitations/{invitation_id}/accept", response_model=AcceptOut)
def accept(invitation_id: uuid.UUID, db: DB, user: CurrentUser):
    inv, vol = svc.accept_invitation(db, user, invitation_id)
    db.commit()
    return AcceptOut(invitation=InvitationOut.model_validate(inv), volunteer=VolunteerOut.model_validate(vol))


@router.post("/invitations/{invitation_id}/decline", response_model=InvitationOut)
def decline(invitation_id: uuid.UUID, db: DB, user: CurrentUser):
    inv = svc.decline_invitation(db, user, invitation_id)
    db.commit()
    return inv


@router.post("/invitations/{invitation_id}/revoke", response_model=InvitationOut)
def revoke(invitation_id: uuid.UUID, db: DB, admin: AdminUser):
    inv = svc.revoke_invitation(db, admin, invitation_id)
    db.commit()
    return inv


# ---- volunteering -----------------------------------------------------------------------------------
@router.post("/topics/{topic_id}/volunteer", response_model=VolunteerOut, status_code=201)
def volunteer(topic_id: uuid.UUID, db: DB, user: CurrentUser):
    _open_topic_for(user, db.get(Topic, topic_id))
    vol = svc.join_topic(db, user, topic_id, via="self")
    db.commit()
    return vol


@router.delete("/topics/{topic_id}/volunteer", status_code=204)
def leave(topic_id: uuid.UUID, db: DB, user: CurrentUser):
    svc.leave_topic(db, user, topic_id)
    db.commit()


@router.get("/topics/{topic_id}/volunteers", response_model=Page[VolunteerAdminOut])
def list_volunteers(topic_id: uuid.UUID, db: DB, _: AdminUser, params: PageParams = Depends()):
    stmt = select(Volunteer, User.email, User.display_name).join(User, User.id == Volunteer.user_id)\
        .where(Volunteer.topic_id == topic_id).order_by(Volunteer.joined_at, Volunteer.id)
    total = db.scalar(select(func.count()).select_from(Volunteer).where(Volunteer.topic_id == topic_id)) or 0
    rows = db.execute(stmt.limit(params.limit).offset(params.offset)).all()
    items = [VolunteerAdminOut(**VolunteerOut.model_validate(v).model_dump(), email=e, display_name=n) for v, e, n in rows]
    return Page(items=items, total=total, limit=params.limit, offset=params.offset)


@router.get("/me/assignments", response_model=list[MyAssignmentOut])
def my_assignments(db: DB, user: CurrentUser, status: AssignmentStatus | None = None):
    stmt = select(Assignment, Topic.title).join(Topic, Topic.id == Assignment.topic_id).where(Assignment.user_id == user.id)\
        .order_by(Assignment.due_at, Assignment.id)
    if status:
        stmt = stmt.where(Assignment.status == status)
    return [MyAssignmentOut(**AssignmentOut.model_validate(a).model_dump(), topic_title=t) for a, t in db.execute(stmt).all()]


@router.get("/me/volunteering", response_model=list[VolunteerOut])
def my_volunteering(db: DB, user: CurrentUser):
    return list(db.scalars(select(Volunteer).where(Volunteer.user_id == user.id).order_by(Volunteer.joined_at.desc())))


@router.post("/assignments/{assignment_id}/complete", response_model=AssignmentOut)
def complete(assignment_id: uuid.UUID, db: DB, user: CurrentUser):
    a = svc.complete_assignment(db, user, assignment_id)
    db.commit()
    return a
