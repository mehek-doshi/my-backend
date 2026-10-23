"""Gamification agent: awards badges from counted facts. Never from LLM output, never from user claims."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import (ArtifactStatus, AssignmentStatus, BadgeCriterion, Stage, TopicOrigin, TopicStatus,
                          VolunteerStatus)
from app.db.models import Artifact, Assignment, Badge, Topic, TopicTestCase, User, UserBadge, Volunteer
from app.services.notifications import notify


class GamificationAgent:
    name = "gamification"

    def counts(self, db: Session, user: User) -> dict[BadgeCriterion, int]:
        def n(stmt) -> int:
            return db.scalar(stmt) or 0
        open_topic = (TopicStatus.OPEN_FOR_VOLUNTEERS, TopicStatus.IN_PROGRESS, TopicStatus.ARCHIVED)
        return {
            BadgeCriterion.VOLUNTEER: n(select(func.count()).select_from(Volunteer).where(
                Volunteer.user_id == user.id, Volunteer.status.in_([VolunteerStatus.ACTIVE, VolunteerStatus.COMPLETED]))),
            BadgeCriterion.TESTCASES: n(select(func.count()).select_from(TopicTestCase).where(TopicTestCase.author_id == user.id)),
            BadgeCriterion.ARTIFACTS: n(select(func.count()).select_from(Artifact).where(
                Artifact.author_id == user.id, Artifact.status == ArtifactStatus.APPROVED)),
            BadgeCriterion.PRESENTATIONS: n(select(func.count()).select_from(Assignment).where(
                Assignment.user_id == user.id, Assignment.stage == Stage.PRESENTATION, Assignment.status == AssignmentStatus.COMPLETED)),
            BadgeCriterion.TOPICS: n(select(func.count()).select_from(Topic).where(
                Topic.requested_by == user.id, Topic.origin == TopicOrigin.CUSTOM, Topic.status.in_(open_topic))),
        }

    def evaluate(self, db: Session, user: User) -> list[Badge]:
        counts = self.counts(db, user)
        have = set(db.scalars(select(UserBadge.badge_id).where(UserBadge.user_id == user.id)))
        awarded: list[Badge] = []
        for badge in db.scalars(select(Badge).where(Badge.active.is_(True))):
            if badge.id not in have and counts.get(badge.criterion, 0) >= badge.threshold:
                db.add(UserBadge(user_id=user.id, badge_id=badge.id))
                notify(db, user.id, "badge_awarded", f"You earned the '{badge.name}' badge", badge.description,
                       dedupe_key=f"badge:{badge.id}", payload={"badge_id": str(badge.id)}, external=False)
                awarded.append(badge)
        db.flush()
        return awarded
