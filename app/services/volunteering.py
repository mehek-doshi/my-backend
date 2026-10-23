"""Invitations, volunteers and stage assignments (Study -> POC -> Presentation) with deadlines."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.gamification import GamificationAgent
from app.core.errors import Conflict, Forbidden, Gone, InvalidState, NotFound
from app.db.enums import (STAGE_ORDER, ArtifactStatus, AssignmentStatus, InvitationStatus, Stage, TopicStatus,
                          VolunteerStatus)
from app.db.models import Artifact, Assignment, Invitation, Topic, User, Volunteer
from app.db.types import utcnow
from app.services.app_settings import RuntimeSettings, load_settings, stage_days
from app.services.audit import audit
from app.services.certificates import issue_certificate
from app.services.lifecycle import move_topic
from app.services.notifications import notify

OPEN_STATUSES = (TopicStatus.OPEN_FOR_VOLUNTEERS, TopicStatus.IN_PROGRESS)


def _lock_topic(db: Session, topic_id: uuid.UUID) -> Topic:
    topic = db.execute(select(Topic).where(Topic.id == topic_id).with_for_update()).scalar_one_or_none()
    if topic is None:
        raise NotFound("Topic not found")
    return topic


def capacity(topic: Topic, runtime: RuntimeSettings) -> int:
    return topic.max_volunteers or runtime.max_volunteers


def _ensure_stage(db: Session, vol: Volunteer, stage: Stage, runtime: RuntimeSettings) -> Assignment:
    due = utcnow() + timedelta(days=stage_days(runtime)[stage.value])
    a = db.scalar(select(Assignment).where(Assignment.volunteer_id == vol.id, Assignment.stage == stage))
    if a is None:
        a = Assignment(volunteer_id=vol.id, topic_id=vol.topic_id, user_id=vol.user_id, stage=stage, due_at=due)
        db.add(a)
    elif a.status == AssignmentStatus.CANCELLED:
        a.status, a.due_at, a.started_at, a.completed_at, a.last_reminded_at = AssignmentStatus.OPEN, due, utcnow(), None, None
    db.flush()
    return a


def _activate(db: Session, vol: Volunteer, topic: Topic, runtime: RuntimeSettings) -> None:
    vol.status = VolunteerStatus.ACTIVE
    _ensure_stage(db, vol, Stage.STUDY, runtime)
    if topic.status == TopicStatus.OPEN_FOR_VOLUNTEERS:
        move_topic(topic, TopicStatus.IN_PROGRESS)


def join_topic(db: Session, user: User, topic_id: uuid.UUID, via: str = "self", invitation: Invitation | None = None) -> Volunteer:
    topic = _lock_topic(db, topic_id)
    if topic.status not in OPEN_STATUSES:
        raise InvalidState("This topic is not open for volunteers")
    runtime = load_settings(db)
    vol = db.scalar(select(Volunteer).where(Volunteer.topic_id == topic.id, Volunteer.user_id == user.id))
    if vol is not None and vol.status != VolunteerStatus.REMOVED:
        raise Conflict("You have already joined this topic")
    active = db.scalar(select(func.count()).select_from(Volunteer).where(
        Volunteer.topic_id == topic.id, Volunteer.status == VolunteerStatus.ACTIVE)) or 0
    if vol is None:
        vol = Volunteer(topic_id=topic.id, user_id=user.id, joined_via=via, invitation_id=invitation.id if invitation else None)
        db.add(vol)
    else:
        vol.joined_via, vol.joined_at, vol.left_at = via, utcnow(), None
    vol.status = VolunteerStatus.WAITLISTED
    db.flush()
    if active < capacity(topic, runtime):
        _activate(db, vol, topic, runtime)
        notify(db, user.id, "volunteer_joined", f"You joined '{topic.title}'", "Your Study stage is open.",
               dedupe_key=f"joined:{vol.id}:{int(vol.joined_at.timestamp())}")
    else:
        notify(db, user.id, "volunteer_waitlisted", f"You are on the waitlist for '{topic.title}'",
               "We will tell you when a place opens up.", dedupe_key=f"waitlist:{vol.id}:{int(vol.joined_at.timestamp())}")
    audit(db, user, "volunteer.join", "topic", topic.id, {"via": via, "status": vol.status.value})
    db.flush()
    GamificationAgent().evaluate(db, user)
    return vol


def leave_topic(db: Session, user: User, topic_id: uuid.UUID) -> None:
    topic = _lock_topic(db, topic_id)
    vol = db.scalar(select(Volunteer).where(Volunteer.topic_id == topic.id, Volunteer.user_id == user.id))
    if vol is None or vol.status not in (VolunteerStatus.ACTIVE, VolunteerStatus.WAITLISTED):
        raise NotFound("You are not volunteering on this topic")
    was_active = vol.status == VolunteerStatus.ACTIVE
    vol.status, vol.left_at = VolunteerStatus.REMOVED, utcnow()
    for a in db.scalars(select(Assignment).where(Assignment.volunteer_id == vol.id, Assignment.status == AssignmentStatus.OPEN)):
        a.status = AssignmentStatus.CANCELLED
    audit(db, user, "volunteer.leave", "topic", topic.id)
    db.flush()  # sessions run with autoflush off: make the change visible to the capacity count
    if was_active:
        promote_waitlist(db, topic)


def promote_waitlist(db: Session, topic: Topic) -> None:
    runtime = load_settings(db)
    active = db.scalar(select(func.count()).select_from(Volunteer).where(
        Volunteer.topic_id == topic.id, Volunteer.status == VolunteerStatus.ACTIVE)) or 0
    if active >= capacity(topic, runtime):
        return
    nxt = db.scalar(select(Volunteer).where(Volunteer.topic_id == topic.id, Volunteer.status == VolunteerStatus.WAITLISTED)
                    .order_by(Volunteer.joined_at, Volunteer.id).limit(1))
    if nxt is None:
        return
    _activate(db, nxt, topic, runtime)
    notify(db, nxt.user_id, "volunteer_promoted", f"A place opened up on '{topic.title}'", "Your Study stage is now open.",
           dedupe_key=f"promoted:{nxt.id}:{int(utcnow().timestamp())}")


# ---- invitations ----------------------------------------------------------------------------------
def invite_users(db: Session, admin: User, topic: Topic, users: list[User]) -> list[Invitation]:
    if topic.status not in OPEN_STATUSES:
        raise InvalidState("You can only invite people to topics that are open for volunteers")
    runtime = load_settings(db)
    expires = utcnow() + timedelta(days=runtime.invitation_expiry_days)
    out: list[Invitation] = []
    for user in users:
        if not user.is_active:
            continue
        inv = db.scalar(select(Invitation).where(Invitation.topic_id == topic.id, Invitation.user_id == user.id))
        vol = db.scalar(select(Volunteer).where(Volunteer.topic_id == topic.id, Volunteer.user_id == user.id,
                                                Volunteer.status != VolunteerStatus.REMOVED))
        if vol is not None or (inv is not None and inv.status in (InvitationStatus.PENDING, InvitationStatus.ACCEPTED)):
            continue  # idempotent: already invited / already in
        if inv is None:
            inv = Invitation(topic_id=topic.id, user_id=user.id, invited_by=admin.id, expires_at=expires)
            db.add(inv)
        else:
            inv.status, inv.expires_at, inv.invited_by, inv.responded_at = InvitationStatus.PENDING, expires, admin.id, None
            inv.reminder_count, inv.last_reminded_at = 0, None
        db.flush()
        notify(db, user.id, "invitation", f"You are invited to '{topic.title}'", "Open Tech Radar to accept or decline.",
               dedupe_key=f"invite:{inv.id}:{int(expires.timestamp())}", payload={"invitation_id": str(inv.id), "topic_id": str(topic.id)})
        out.append(inv)
    audit(db, admin, "invitation.create", "topic", topic.id, {"count": len(out)})
    return out


def _own_invitation(db: Session, user: User, invitation_id: uuid.UUID) -> Invitation:
    inv = db.get(Invitation, invitation_id)
    if inv is None or inv.user_id != user.id:
        raise NotFound("Invitation not found")  # never reveal other people's invitations
    return inv


def _check_pending(db: Session, inv: Invitation) -> None:
    if inv.status != InvitationStatus.PENDING:
        raise InvalidState(f"This invitation is already {inv.status.value}")
    if inv.expires_at <= utcnow():
        inv.status = InvitationStatus.EXPIRED
        db.commit()
        raise Gone("This invitation has expired")


def accept_invitation(db: Session, user: User, invitation_id: uuid.UUID) -> tuple[Invitation, Volunteer]:
    inv = _own_invitation(db, user, invitation_id)
    _check_pending(db, inv)
    vol = join_topic(db, user, inv.topic_id, via="invitation", invitation=inv)
    inv.status, inv.responded_at = InvitationStatus.ACCEPTED, utcnow()
    return inv, vol


def decline_invitation(db: Session, user: User, invitation_id: uuid.UUID) -> Invitation:
    inv = _own_invitation(db, user, invitation_id)
    _check_pending(db, inv)
    inv.status, inv.responded_at = InvitationStatus.DECLINED, utcnow()
    audit(db, user, "invitation.decline", "invitation", inv.id)
    return inv


def revoke_invitation(db: Session, admin: User, invitation_id: uuid.UUID) -> Invitation:
    inv = db.get(Invitation, invitation_id)
    if inv is None:
        raise NotFound("Invitation not found")
    if inv.status != InvitationStatus.PENDING:
        raise InvalidState(f"Only pending invitations can be revoked (this one is {inv.status.value})")
    inv.status, inv.responded_at = InvitationStatus.REVOKED, utcnow()
    audit(db, admin, "invitation.revoke", "invitation", inv.id)
    return inv


def expire_invitations(db: Session) -> int:
    n = 0
    for inv in db.scalars(select(Invitation).where(Invitation.status == InvitationStatus.PENDING, Invitation.expires_at <= utcnow())):
        inv.status = InvitationStatus.EXPIRED
        n += 1
    return n


# ---- assignments -------------------------------------------------------------------------------------
def complete_assignment(db: Session, user: User, assignment_id: uuid.UUID) -> Assignment:
    a = db.get(Assignment, assignment_id)
    if a is None or a.user_id != user.id:
        raise NotFound("Assignment not found")
    if a.status != AssignmentStatus.OPEN:
        raise InvalidState(f"This stage is already {a.status.value}")
    vol = db.get(Volunteer, a.volunteer_id)
    if vol.status != VolunteerStatus.ACTIVE:
        raise InvalidState("You are not an active volunteer on this topic")
    if a.stage == Stage.PRESENTATION:
        approved = db.scalar(select(func.count()).select_from(Artifact).where(
            Artifact.author_id == user.id, Artifact.topic_id == a.topic_id, Artifact.status == ArtifactStatus.APPROVED)) or 0
        if not approved:
            raise InvalidState("Finish the Presentation stage after at least one of your artifacts for this topic is approved")
    a.status, a.completed_at = AssignmentStatus.COMPLETED, utcnow()
    idx = STAGE_ORDER.index(a.stage)
    topic = db.get(Topic, a.topic_id)
    if idx + 1 < len(STAGE_ORDER):
        nxt = _ensure_stage(db, vol, STAGE_ORDER[idx + 1], load_settings(db))
        notify(db, user.id, "stage_open", f"Next stage: {nxt.stage.value}", f"'{topic.title}' - due {nxt.due_at:%Y-%m-%d}",
               dedupe_key=f"stage:{nxt.id}")
    else:
        vol.status = VolunteerStatus.COMPLETED
        cert = issue_certificate(db, user, topic)
        notify(db, user.id, "certificate", f"Your certificate for '{topic.title}' is ready", cert.serial,
               dedupe_key=f"cert:{cert.id}", payload={"certificate_id": str(cert.id)})
        promote_waitlist(db, topic)
    audit(db, user, "assignment.complete", "assignment", a.id, {"stage": a.stage.value})
    db.flush()
    GamificationAgent().evaluate(db, user)
    return a
