import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select

from app.agents.classification import ClassificationAgent
from app.agents.extraction import ArticleExtractionAgent
from app.agents.guardrails import GuardrailAgent
from app.agents.types import Candidate
from app.agents.verification import VerificationAgent
from app.api.deps import DB, AdminUser, CurrentUser
from app.core.errors import Forbidden, NotFound, Unprocessable
from app.core.services import Services, get_services
from app.core.textutil import clean_text
from app.db.enums import Role, TopicOrigin, TopicStatus
from app.db.models import Category, SourceArticle, Topic, TopicTestCase, User
from app.schemas.common import Page, PageParams, paginate
from app.schemas.topics import (ApproveIn, ArticleOut, CustomTopicIn, MergeIn, RejectIn, TestCaseIn, TestCaseOut,
                                TopicAdminOut, TopicDetail, TopicOut, VerifyIn)
from app.agents.deduplication import DeduplicationAgent
from app.core.config import get_settings
from app.security.ssrf import BlockedURLError, FetchError, validate_url
from app.services import topics as svc
from app.services.app_settings import load_settings
from app.services.audit import audit
from app.services.lifecycle import TOPIC_PUBLIC

router = APIRouter(prefix="/topics", tags=["topics"])

REVIEWERS = (Role.ADMIN,)


def _visible(user: User, topic: Topic) -> bool:
    if user.role in REVIEWERS:
        return True
    return topic.status in TOPIC_PUBLIC or topic.requested_by == user.id


def _out(user: User, topic: Topic):
    if user.role in REVIEWERS:
        return TopicAdminOut.model_validate(topic)
    out = TopicOut.model_validate(topic)
    return out


def _load(db, user: User, topic_id: uuid.UUID) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None or not _visible(user, topic):  # 404, not 403: do not reveal that it exists
        raise NotFound("Topic not found")
    return topic


@router.get("", response_model=Page[TopicOut | TopicAdminOut])
def list_topics(db: DB, user: CurrentUser, params: PageParams = Depends(), status: TopicStatus | None = None,
                category_id: uuid.UUID | None = None, q: str | None = None, mine: bool = False):
    stmt = select(Topic).order_by(Topic.detected_at.desc(), Topic.id)
    if user.role not in REVIEWERS:
        stmt = stmt.where(or_(Topic.status.in_(list(TOPIC_PUBLIC)), Topic.requested_by == user.id))
    if mine:
        stmt = stmt.where(Topic.requested_by == user.id)
    if status:
        stmt = stmt.where(Topic.status == status)
    if category_id:
        stmt = stmt.where(Topic.category_id == category_id)
    if q:
        like = f"%{q.strip()[:100].lower()}%"
        from sqlalchemy import func
        stmt = stmt.where(or_(func.lower(Topic.title).like(like), func.lower(Topic.summary).like(like)))
    rows, total = paginate(db, stmt, params)
    return Page(items=[_out(user, t) for t in rows], total=total, limit=params.limit, offset=params.offset)


@router.get("/{topic_id}", response_model=TopicDetail)
def get_topic(topic_id: uuid.UUID, db: DB, user: CurrentUser):
    topic = _load(db, user, topic_id)
    arts = list(db.scalars(select(SourceArticle).where(SourceArticle.topic_id == topic.id).order_by(SourceArticle.fetched_at)))
    return TopicDetail(topic=_out(user, topic), articles=[ArticleOut.model_validate(a) for a in arts])


@router.post("/custom", response_model=TopicOut, status_code=201)
def create_custom_topic(body: CustomTopicIn, db: DB, user: CurrentUser, services: Services = Depends(get_services)):
    """An employee suggests a topic. It is published once its source is verified and it passes the guardrails; if it has no
    category, or looks like a duplicate, it waits for an Admin."""
    runtime = load_settings(db)
    if body.category_id:
        cat = db.get(Category, body.category_id)
        if cat is None or cat.retired:
            raise Unprocessable("Category not found")
    cand = Candidate(title=clean_text(body.title, 300), url=str(body.source_url) if body.source_url else "",
                     raw_summary=clean_text(body.summary, 2000), summary=clean_text(body.summary, 600),
                     category_id=body.category_id)
    if cand.url:
        try:
            validate_url(cand.url, allowed_ports=get_settings().fetch_port_list)
        except BlockedURLError as exc:
            raise Unprocessable(f"This URL is not allowed: {exc}") from exc
        except FetchError:
            pass  # unresolvable host: stored as an unverified topic with the reason recorded
        ArticleExtractionAgent(services.fetcher).extract(cand)
    DeduplicationAgent().check(db, cand, runtime)
    if cand.duplicate_of:
        from app.core.errors import Conflict
        raise Conflict("A very similar topic already exists", details={"topic_id": str(cand.duplicate_of)})
    if cand.category_id is None:
        ClassificationAgent().classify(cand, list(db.scalars(select(Category))))
    GuardrailAgent().check(cand, runtime, require_enrichment=False)
    VerificationAgent().verify_candidate(cand, runtime)
    topic = svc.persist_candidate(db, cand, origin=TopicOrigin.CUSTOM, requested_by=user.id)
    audit(db, user, "topic.custom_submitted", "topic", topic.id, {"status": topic.status.value})
    db.commit()
    return TopicOut.model_validate(topic)


# ---- reviewer actions (Admin) ------------------------------------------------------------
@router.post("/{topic_id}/approve", response_model=TopicAdminOut)
def approve(topic_id: uuid.UUID, body: ApproveIn, db: DB, admin: AdminUser):
    topic = svc.get_topic(db, topic_id)
    svc.approve_topic(db, topic, admin, comment=body.comment, category_id=body.category_id, max_volunteers=body.max_volunteers)
    db.commit()
    return topic


@router.post("/{topic_id}/reject", response_model=TopicAdminOut)
def reject(topic_id: uuid.UUID, body: RejectIn, db: DB, admin: AdminUser):
    topic = svc.get_topic(db, topic_id)
    svc.reject_topic(db, topic, admin, body.reason)
    db.commit()
    return topic


@router.post("/{topic_id}/merge", response_model=TopicAdminOut)
def merge(topic_id: uuid.UUID, body: MergeIn, db: DB, admin: AdminUser):
    topic = svc.get_topic(db, topic_id)
    svc.merge_topic(db, topic, body.target_topic_id, admin, body.comment)
    db.commit()
    return topic


@router.post("/{topic_id}/verify", response_model=TopicAdminOut)
def verify_manually(topic_id: uuid.UUID, body: VerifyIn, db: DB, admin: AdminUser):
    topic = svc.get_topic(db, topic_id)
    svc.manually_verify(db, topic, admin, body.comment)
    db.commit()
    return topic


@router.post("/{topic_id}/reverify", response_model=TopicAdminOut)
def reverify(topic_id: uuid.UUID, db: DB, admin: AdminUser, services: Services = Depends(get_services)):
    topic = svc.get_topic(db, topic_id)
    svc.reverify(db, topic, admin, services.fetcher, load_settings(db))
    db.commit()
    return topic


# ---- reusable test cases ---------------------------------------------------------------------
@router.get("/{topic_id}/test-cases", response_model=list[TestCaseOut])
def list_test_cases(topic_id: uuid.UUID, db: DB, user: CurrentUser):
    topic = _load(db, user, topic_id)
    return list(db.scalars(select(TopicTestCase).where(TopicTestCase.topic_id == topic.id).order_by(TopicTestCase.created_at)))


@router.post("/{topic_id}/test-cases", response_model=TestCaseOut, status_code=201)
def add_test_case(topic_id: uuid.UUID, body: TestCaseIn, db: DB, user: CurrentUser):
    topic = _load(db, user, topic_id)
    if topic.status not in TOPIC_PUBLIC:
        raise Forbidden("Test cases can only be added to topics that are open for work")
    tc = TopicTestCase(topic_id=topic.id, author_id=user.id, title=clean_text(body.title, 300),
                       url=str(body.url) if body.url else None,
                       description=clean_text(body.description, 4000) if body.description else None)
    db.add(tc)
    db.commit()
    return tc


@router.delete("/{topic_id}/test-cases/{case_id}", status_code=204)
def delete_test_case(topic_id: uuid.UUID, case_id: uuid.UUID, db: DB, user: CurrentUser):
    topic = _load(db, user, topic_id)
    tc = db.get(TopicTestCase, case_id)
    if tc is None or tc.topic_id != topic.id:
        raise NotFound("Test case not found")
    if tc.author_id != user.id and user.role != Role.ADMIN:
        raise Forbidden("You can only remove your own test cases")
    audit(db, user, "test_case.delete", "test_case", tc.id)
    db.delete(tc)
    db.commit()
