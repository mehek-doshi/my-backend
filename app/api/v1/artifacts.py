import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select

from app.agents.ingestion import IngestionAgent
from app.api.deps import DB, CurrentUser, ReviewerUser
from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound
from app.db.enums import ArtifactStatus, ArtifactType, Role
from app.db.models import Artifact, Topic
from app.schemas.common import Page, PageParams, paginate
from app.schemas.workflow import ArtifactOut, ArtifactReviewOut, ReasonIn, ReviewDecisionIn
from app.services import artifacts as svc
from app.services.dispatch import enqueue_artifact_scan
from app.storage.local import LocalStorage

router = APIRouter(tags=["artifacts"])


def _view(user, art: Artifact):
    """Authors and reviewers see the scan report; everybody else sees the public fields only."""
    if art.author_id == user.id or user.role == Role.ADMIN:
        return ArtifactReviewOut.model_validate(art)
    return ArtifactOut.model_validate(art)


def _visible(user, art: Artifact) -> Artifact:
    if not svc.can_view(user, art):
        raise NotFound("Artifact not found")  # do not reveal other people's private submissions
    return art


@router.post("/artifacts", response_model=ArtifactReviewOut, status_code=202)
def submit(db: DB, user: CurrentUser, title: str = Form(min_length=3, max_length=300), summary: str = Form("", max_length=4000),
           type: ArtifactType = Form(...), topic_id: uuid.UUID | None = Form(None), assignment_id: uuid.UUID | None = Form(None),
           repo_url: str | None = Form(None, max_length=2048), file: UploadFile | None = File(None)):
    """Submit a file and/or a repository link. The file is checked on arrival, then scanned by a worker; an Admin reviews it
    only after it passed the scan. Nothing is visible to others until an Admin approves it."""
    settings = get_settings()
    agent = IngestionAgent(settings)
    received = agent.receive(file.filename or "", file.file) if file is not None and file.filename else None
    art = svc.create_artifact(db, user, title=title, summary=summary, type_=type, topic_id=topic_id, assignment_id=assignment_id,
                              repo_url=repo_url or None, received=received, storage=agent.storage)
    db.commit()
    enqueue_artifact_scan(art.id)
    db.refresh(art)
    return art


@router.put("/artifacts/{artifact_id}/file", response_model=ArtifactReviewOut, status_code=202)
def replace(artifact_id: uuid.UUID, db: DB, user: CurrentUser, file: UploadFile = File(...)):
    art = svc.get_artifact(db, artifact_id)
    if art.author_id != user.id:
        raise NotFound("Artifact not found")
    agent = IngestionAgent(get_settings())
    received = agent.receive(file.filename or "", file.file)
    svc.replace_file(db, user, art, received, agent.storage)
    db.commit()
    enqueue_artifact_scan(art.id)
    db.refresh(art)
    return art


@router.get("/artifacts/mine", response_model=Page[ArtifactReviewOut])
def my_artifacts(db: DB, user: CurrentUser, params: PageParams = Depends(), status: ArtifactStatus | None = None):
    stmt = select(Artifact).where(Artifact.author_id == user.id).order_by(Artifact.created_at.desc(), Artifact.id)
    if status:
        stmt = stmt.where(Artifact.status == status)
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.get("/library", response_model=Page[ArtifactOut])
def library(db: DB, _: CurrentUser, params: PageParams = Depends(), topic_id: uuid.UUID | None = None, type: ArtifactType | None = None,
            category_id: uuid.UUID | None = None, q: str | None = None):
    """Approved artifacts only."""
    stmt = select(Artifact).where(Artifact.status == ArtifactStatus.APPROVED).order_by(Artifact.published_at.desc(), Artifact.id)
    if topic_id:
        stmt = stmt.where(Artifact.topic_id == topic_id)
    if type:
        stmt = stmt.where(Artifact.type == type)
    if category_id:
        stmt = stmt.join(Topic, Topic.id == Artifact.topic_id).where(Topic.category_id == category_id)
    if q:
        like = f"%{q.strip()[:100].lower()}%"
        stmt = stmt.where(or_(func.lower(Artifact.title).like(like), func.lower(Artifact.summary).like(like)))
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.get("/artifacts/{artifact_id}", response_model=ArtifactReviewOut | ArtifactOut)
def get_artifact(artifact_id: uuid.UUID, db: DB, user: CurrentUser):
    return _view(user, _visible(user, svc.get_artifact(db, artifact_id)))


@router.get("/artifacts/{artifact_id}/download")
def download(artifact_id: uuid.UUID, db: DB, user: CurrentUser):
    art = _visible(user, svc.get_artifact(db, artifact_id))
    if not art.storage_key or not art.filename:
        raise NotFound("This artifact has no file")
    path = LocalStorage().path_for(art.storage_key)
    if not path.is_file():
        raise NotFound("The file is no longer available")
    return FileResponse(path, media_type="application/octet-stream", filename=art.filename,
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"})


# ---- moderation (Admin) ------------------------------------------------------------------
@router.get("/moderation/artifacts", response_model=Page[ArtifactReviewOut])
def moderation_queue(db: DB, _: ReviewerUser, params: PageParams = Depends(),
                     status: ArtifactStatus = ArtifactStatus.PENDING_REVIEW):
    rows, total = paginate(db, select(Artifact).where(Artifact.status == status).order_by(Artifact.created_at, Artifact.id), params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.post("/artifacts/{artifact_id}/approve", response_model=ArtifactReviewOut)
def approve(artifact_id: uuid.UUID, body: ReviewDecisionIn, db: DB, reviewer: ReviewerUser):
    art = svc.approve_artifact(db, svc.get_artifact(db, artifact_id), reviewer, body.comment)
    db.commit()
    return art


@router.post("/artifacts/{artifact_id}/reject", response_model=ArtifactReviewOut)
def reject(artifact_id: uuid.UUID, body: ReasonIn, db: DB, reviewer: ReviewerUser):
    art = svc.reject_artifact(db, svc.get_artifact(db, artifact_id), reviewer, body.reason)
    db.commit()
    return art


@router.post("/artifacts/{artifact_id}/quarantine", response_model=ArtifactReviewOut)
def quarantine(artifact_id: uuid.UUID, body: ReasonIn, db: DB, reviewer: ReviewerUser):
    art = svc.quarantine_artifact(db, svc.get_artifact(db, artifact_id), reviewer, body.reason)
    db.commit()
    return art
