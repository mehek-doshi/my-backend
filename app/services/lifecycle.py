"""Explicit lifecycle state machines for topics and artifacts.

Every status change goes through these functions, so an invalid jump (for example publishing an
unverified topic or approving an artifact that failed its scan) raises InvalidState instead of
silently succeeding.
"""
from __future__ import annotations

from app.core.errors import InvalidState
from app.db.enums import ArtifactStatus as A
from app.db.enums import TopicStatus as T
from app.db.models import Artifact, Topic

TOPIC_TRANSITIONS: dict[T, set[T]] = {
    T.DISCOVERED: {T.ENRICHED, T.BLOCKED},
    T.ENRICHED: {T.CLASSIFIED, T.BLOCKED},
    T.CLASSIFIED: {T.BLOCKED, T.UNVERIFIED, T.PENDING_REVIEW, T.OPEN_FOR_VOLUNTEERS},
    T.UNVERIFIED: {T.PENDING_REVIEW, T.REJECTED},
    T.BLOCKED: {T.REJECTED, T.ARCHIVED},
    T.PENDING_REVIEW: {T.OPEN_FOR_VOLUNTEERS, T.REJECTED, T.MERGED, T.UNVERIFIED},
    T.OPEN_FOR_VOLUNTEERS: {T.IN_PROGRESS, T.ARCHIVED},
    T.IN_PROGRESS: {T.OPEN_FOR_VOLUNTEERS, T.ARCHIVED},
    T.REJECTED: set(),
    T.MERGED: set(),
    T.ARCHIVED: set(),
}

# statuses an employee is allowed to see
TOPIC_PUBLIC = {T.OPEN_FOR_VOLUNTEERS, T.IN_PROGRESS}

ARTIFACT_TRANSITIONS: dict[A, set[A]] = {
    A.SUBMITTED: {A.SCANNING},
    A.SCANNING: {A.QUARANTINED, A.PENDING_REVIEW},
    A.QUARANTINED: {A.SUBMITTED},          # only by replacing the file
    A.PENDING_REVIEW: {A.APPROVED, A.REJECTED, A.QUARANTINED},
    A.APPROVED: set(),
    A.REJECTED: {A.SUBMITTED},             # resubmission with a new file
}


def move_topic(topic: Topic, new: T) -> None:
    if new not in TOPIC_TRANSITIONS[topic.status]:
        raise InvalidState(f"A topic cannot move from '{topic.status.value}' to '{new.value}'")
    if new == T.OPEN_FOR_VOLUNTEERS and topic.status in (T.PENDING_REVIEW, T.CLASSIFIED):
        # never publish something unverified or something a guardrail stopped
        if not topic.verified:
            raise InvalidState("This topic has no verified source, so it cannot be published")
        if topic.guardrail.get("passed") is not True:
            raise InvalidState("This topic did not pass the guardrails, so it cannot be published")
    topic.status = new


def move_artifact(artifact: Artifact, new: A) -> None:
    if new not in ARTIFACT_TRANSITIONS[artifact.status]:
        raise InvalidState(f"An artifact cannot move from '{artifact.status.value}' to '{new.value}'")
    if new == A.APPROVED:
        scan = artifact.scan_result or {}
        if not scan or scan.get("blocked"):
            raise InvalidState("This artifact has not passed its security scan, so it cannot be approved")
    artifact.status = new
