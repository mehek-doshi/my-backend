"""Artifact submission, scanning and moderation."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.agents.gamification import GamificationAgent
from app.agents.ingestion import IngestionAgent, Received
from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, InvalidState, NotFound, Unprocessable
from app.core.textutil import clean_text
from app.db.enums import (ArtifactStatus, ArtifactType, AssignmentStatus, ModerationDecision, Role, Stage,
                          VolunteerStatus)
from app.db.models import Artifact, Assignment, ModerationRecord, Topic, User, Volunteer
from app.db.types import utcnow
from app.security.ssrf import BlockedURLError, FetchError, validate_url
from app.services.audit import audit
from app.services.lifecycle import move_artifact
from app.services.notifications import notify
from app.storage.local import LocalStorage


def _check_repo_url(url: str | None) -> None:
    if not url:
        return
    try:
        validate_url(url, allowed_ports=get_settings().fetch_port_list)
    except BlockedURLError as exc:
        raise Unprocessable(f"The repository link is not allowed: {exc}") from exc
    except FetchError:
        pass  # DNS failure now is not a reason to refuse a link we never fetch


def _store(art: Artifact, rec: Received, storage: LocalStorage) -> None:
    key = f"artifacts/{art.id}/v{art.version}/{rec.filename}"
    storage.commit(rec.tmp_path, key)
    art.filename, art.size_bytes, art.sha256, art.storage_key = rec.filename, rec.size, rec.sha256, key
    art.content_type = "application/octet-stream"


def create_artifact(db: Session, user: User, *, title: str, summary: str, type_: ArtifactType, topic_id: uuid.UUID | None,
                    assignment_id: uuid.UUID | None, repo_url: str | None, received: Received | None,
                    storage: LocalStorage | None = None) -> Artifact:
    storage = storage or LocalStorage()
    try:
        if received is None and not repo_url:
            raise Unprocessable("Upload a file or give a repository link")
        _check_repo_url(repo_url)
        stage = None
        if assignment_id:
            a = db.get(Assignment, assignment_id)
            if a is None or a.user_id != user.id:
                raise NotFound("Assignment not found")
            if a.status != AssignmentStatus.OPEN:
                raise Unprocessable("That stage is no longer open")
            if topic_id and topic_id != a.topic_id:
                raise Unprocessable("The assignment belongs to a different topic")
            topic_id, stage = a.topic_id, a.stage
        elif topic_id:
            topic = db.get(Topic, topic_id)
            vol = db.scalar(select(Volunteer).where(Volunteer.topic_id == topic_id, Volunteer.user_id == user.id,
                                                    Volunteer.status.in_([VolunteerStatus.ACTIVE, VolunteerStatus.COMPLETED])))
            if topic is None or vol is None:
                raise Forbidden("You can only submit to topics you are volunteering on")
        art = Artifact(author_id=user.id, topic_id=topic_id, assignment_id=assignment_id, stage=stage, title=clean_text(title, 300),
                       summary=clean_text(summary, 4000), type=type_, repo_url=repo_url)
        db.add(art)
        db.flush()
        if received:
            _store(art, received, storage)
        audit(db, user, "artifact.submit", "artifact", art.id, {"type": type_.value, "size": art.size_bytes, "sha256": art.sha256})
        return art
    except Exception:
        if received:
            received.tmp_path.unlink(missing_ok=True)
        raise


def replace_file(db: Session, user: User, art: Artifact, received: Received, storage: LocalStorage | None = None) -> Artifact:
    storage = storage or LocalStorage()
    try:
        if art.author_id != user.id:
            raise NotFound("Artifact not found")
        if art.status not in (ArtifactStatus.QUARANTINED, ArtifactStatus.REJECTED):
            raise InvalidState("Only a quarantined or rejected artifact can be replaced")
        old_key = art.storage_key
        move_artifact(art, ArtifactStatus.SUBMITTED)
        art.version += 1
        art.scan_result, art.rejection_reason, art.reviewed_by, art.reviewed_at = {}, None, None, None
        _store(art, received, storage)
        if old_key:
            storage.delete(old_key)
        audit(db, user, "artifact.replace", "artifact", art.id, {"version": art.version, "sha256": art.sha256})
        return art
    except Exception:
        received.tmp_path.unlink(missing_ok=True)
        raise


def process_scan(db: Session, artifact_id: uuid.UUID, ingestion: IngestionAgent | None = None) -> Artifact | None:
    """Worker step. Idempotent: only one worker can move SUBMITTED -> SCANNING."""
    claimed = db.execute(update(Artifact).where(Artifact.id == artifact_id, Artifact.status == ArtifactStatus.SUBMITTED)
                         .values(status=ArtifactStatus.SCANNING)).rowcount
    db.commit()
    if not claimed:
        return None
    art = db.get(Artifact, artifact_id)
    ingestion = ingestion or IngestionAgent(get_settings())
    if art.storage_key:
        path = ingestion.storage.path_for(art.storage_key)
        report = ingestion.scan(path).as_dict() if path.is_file() else {"blocked": True, "findings": [
            {"kind": "file_missing", "severity": "block", "file": art.filename or "", "line": None, "detail": ""}]}
    else:  # link-only submission: nothing to scan, say so honestly
        report = {"blocked": False, "files_scanned": 0, "findings": [], "antivirus": {"engine": "none", "status": "not_applicable"},
                  "note": "link only; the repository was not fetched or scanned"}
    report["scanned_at"] = utcnow().isoformat()
    art.scan_result = report
    move_artifact(art, ArtifactStatus.QUARANTINED if report["blocked"] else ArtifactStatus.PENDING_REVIEW)
    if report["blocked"]:
        kinds = sorted({f["kind"] for f in report["findings"]})
        notify(db, art.author_id, "artifact_quarantined", f"'{art.title}' needs changes before review",
               "The automatic checks found: " + ", ".join(kinds) + ". Replace the file to resubmit.", dedupe_key=f"quarantine:{art.id}:{art.version}",
               external=False)
    else:
        for rid in db.scalars(select(User.id).where(User.role == Role.ADMIN, User.is_active.is_(True))):
            if rid != art.author_id:
                notify(db, rid, "artifact_review", f"New artifact to review: '{art.title}'", dedupe_key=f"review:{art.id}:{art.version}")
    audit(db, None, "artifact.scanned", "artifact", art.id, {"blocked": report["blocked"], "findings": len(report["findings"])})
    db.commit()
    return art


def get_artifact(db: Session, artifact_id: uuid.UUID) -> Artifact:
    art = db.get(Artifact, artifact_id)
    if art is None:
        raise NotFound("Artifact not found")
    return art


def can_view(user: User, art: Artifact) -> bool:
    return art.author_id == user.id or user.role == Role.ADMIN or art.status == ArtifactStatus.APPROVED


def _record(db: Session, art: Artifact, reviewer: User, decision: ModerationDecision, reason: str | None) -> None:
    art.reviewed_by, art.reviewed_at = reviewer.id, utcnow()
    db.add(ModerationRecord(artifact_id=art.id, moderator_id=reviewer.id, decision=decision, reason=reason, scan_snapshot=art.scan_result))
    audit(db, reviewer, f"artifact.{decision.value}", "artifact", art.id, {"reason": reason})


def _no_self_review(reviewer: User, art: Artifact) -> None:
    if art.author_id == reviewer.id:
        raise Forbidden("You cannot review your own artifact")


def approve_artifact(db: Session, art: Artifact, reviewer: User, comment: str | None = None) -> Artifact:
    _no_self_review(reviewer, art)
    move_artifact(art, ArtifactStatus.APPROVED)  # refuses unless a clean scan exists
    art.published_at = utcnow()
    _record(db, art, reviewer, ModerationDecision.APPROVED, comment)
    author = db.get(User, art.author_id)
    notify(db, author.id, "artifact_approved", f"'{art.title}' was approved", comment or "", dedupe_key=f"approved:{art.id}")
    db.flush()
    GamificationAgent().evaluate(db, author)
    return art


def reject_artifact(db: Session, art: Artifact, reviewer: User, reason: str) -> Artifact:
    _no_self_review(reviewer, art)
    move_artifact(art, ArtifactStatus.REJECTED)
    art.rejection_reason = reason
    _record(db, art, reviewer, ModerationDecision.REJECTED, reason)
    notify(db, art.author_id, "artifact_rejected", f"'{art.title}' needs changes", reason, dedupe_key=f"rejected:{art.id}:{art.version}")
    return art


def quarantine_artifact(db: Session, art: Artifact, reviewer: User, reason: str) -> Artifact:
    _no_self_review(reviewer, art)
    move_artifact(art, ArtifactStatus.QUARANTINED)
    _record(db, art, reviewer, ModerationDecision.QUARANTINED, reason)
    notify(db, art.author_id, "artifact_quarantined", f"'{art.title}' was held back", reason, dedupe_key=f"held:{art.id}:{art.version}")
    return art
