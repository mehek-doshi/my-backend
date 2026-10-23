"""Discovery workflow.

Scheduler -> Discovery -> Article extraction -> LLM enrichment -> Classification -> Deduplication
-> Guardrails -> Verification -> (stored as pending_review / unverified / blocked) -> Admin review.
The orchestrator never publishes anything: the best a topic can reach here is 'pending_review'.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.classification import ClassificationAgent
from app.agents.deduplication import DeduplicationAgent
from app.agents.discovery import DiscoveryAgent
from app.agents.enrichment import EnrichmentAgent
from app.agents.extraction import ArticleExtractionAgent
from app.agents.guardrails import GuardrailAgent
from app.agents.types import Candidate
from app.agents.verification import VerificationAgent
from app.core.services import Services
from app.core.textutil import clean_text
from app.db.enums import DiscoveryTrigger, EventLevel, RunStatus, SourceKind, TopicOrigin
from app.db.models import AgentRun, Category, DiscoverySession, TechnologySource, Topic
from app.db.types import utcnow
from app.llm.base import LLMError
from app.security.ssrf import FetchError
from app.services.app_settings import RuntimeSettings, load_settings
from app.services.audit import audit
from app.services.runs import RunRecorder, claim_run, create_run, finish_run
from app.services.topics import add_article, persist_candidate

WORKFLOW = "discovery"


def start_discovery(db: Session, trigger: DiscoveryTrigger, *, user=None, bucket: str | None = None) -> tuple[DiscoverySession, bool]:
    """Create the session + run. Scheduled runs use a time-bucket key so a re-delivered task is a no-op."""
    key = f"discovery:{bucket}" if bucket else f"discovery:manual:{uuid.uuid4()}"
    run, created = create_run(db, WORKFLOW, idempotency_key=key, input={"trigger": trigger.value},
                              triggered_by=user.id if user else None)
    if not created:
        existing = db.scalar(select(DiscoverySession).where(DiscoverySession.agent_run_id == run.id))
        db.commit()
        return existing, False
    session = DiscoverySession(trigger=trigger, started_by=user.id if user else None, agent_run_id=run.id)
    db.add(session)
    audit(db, user, "discovery.start", "discovery_session", None, {"trigger": trigger.value, "run_id": run.id})
    db.commit()
    return session, True


def process_candidate(db: Session, cand: Candidate, *, services: Services, runtime: RuntimeSettings, categories: list[Category],
                      session_id: uuid.UUID | None, fetch_page: bool = True) -> tuple[str, Topic | None]:
    """Run one candidate through the pipeline. Returns (outcome, topic)."""
    dedup = DeduplicationAgent()
    # cheap duplicate check first: do not spend an LLM call on something we already hold
    dedup.check(db, cand, runtime)
    if cand.duplicate_of:
        existing = db.get(Topic, cand.duplicate_of)
        if existing is not None:
            add_article(db, existing, cand)
        return "duplicate", existing
    if fetch_page:
        ArticleExtractionAgent(services.fetcher).extract(cand)
    EnrichmentAgent(services.llm).enrich(cand, runtime, [c.name for c in categories if not c.retired])
    ClassificationAgent().classify(cand, categories)
    GuardrailAgent().check(cand, runtime)
    VerificationAgent().verify_candidate(cand, runtime)
    topic = persist_candidate(db, cand, origin=TopicOrigin.AGENT, session_id=session_id)
    return topic.status.value, topic


def execute_discovery(db: Session, session_id: uuid.UUID, services: Services) -> DiscoverySession:
    session = db.get(DiscoverySession, session_id)
    if session is None or session.agent_run_id is None:
        raise ValueError("unknown discovery session")
    run = db.get(AgentRun, session.agent_run_id)
    if not claim_run(db, run.id):
        return session  # someone else is running it, or it already ran
    db.refresh(run)
    session.status, session.started_at = RunStatus.RUNNING, utcnow()
    db.commit()
    rec = RunRecorder(db, run)
    runtime = load_settings(db)
    categories = list(db.scalars(select(Category).where(Category.retired.is_(False))))
    sources = list(db.scalars(select(TechnologySource).where(TechnologySource.kind == SourceKind.FEED)))
    stats = {"sources": len(sources), "sources_failed": 0, "candidates": 0, "created": 0, "duplicates": 0,
             "blocked": 0, "open_for_volunteers": 0, "pending_review": 0, "unverified": 0, "errors": 0}
    rec.event("started", f"Discovery started with {len(sources)} source(s)")
    agent = DiscoveryAgent(services.fetcher, services.search)
    try:
        for source in sources:
            source.last_crawled_at = utcnow()
            try:
                candidates = agent.crawl_source(source)
                source.last_success_at, source.last_error, source.consecutive_failures = utcnow(), None, 0
                db.commit()
            except Exception as exc:  # one broken feed must not stop the run
                db.rollback()
                source = db.get(TechnologySource, source.id)
                source.last_error = f"{exc.__class__.__name__}: {str(exc)[:300]}"
                source.consecutive_failures += 1
                db.commit()
                stats["sources_failed"] += 1
                rec.event("source_failed", f"{source.name}: {source.last_error}", level=EventLevel.WARNING,
                          payload={"source_id": str(source.id)})
                continue
            rec.event("source_crawled", f"{source.name}: {len(candidates)} item(s)", payload={"source_id": str(source.id)})
            for cand in candidates:
                stats["candidates"] += 1
                try:
                    with db.begin_nested():
                        outcome, _topic = process_candidate(db, cand, services=services, runtime=runtime,
                                                            categories=categories, session_id=session.id)
                    db.commit()
                except (LLMError, FetchError) as exc:
                    db.rollback()
                    stats["errors"] += 1
                    rec.event("candidate_failed", f"'{clean_text(cand.title, 80)}': {exc.__class__.__name__}",
                              level=EventLevel.WARNING)
                    continue
                if outcome == "duplicate":
                    stats["duplicates"] += 1
                else:
                    stats["created"] += 1
                    stats[outcome] = stats.get(outcome, 0) + 1
            rec.checkpoint(f"source:{source.id}", {"done": True, "stats": dict(stats)})
    except Exception as exc:
        db.rollback()
        run = db.get(AgentRun, run.id)
        session = db.get(DiscoverySession, session_id)
        session.status, session.finished_at, session.stats = RunStatus.FAILED, utcnow(), stats
        finish_run(db, run, RunStatus.FAILED, stats, f"{exc.__class__.__name__}: {str(exc)[:500]}")
        RunRecorder(db, run).event("failed", f"Discovery failed: {exc.__class__.__name__}", level=EventLevel.ERROR)
        raise
    partial = stats["sources_failed"] or stats["errors"]
    status = RunStatus.PARTIAL if partial and (stats["created"] or stats["duplicates"]) else (
        RunStatus.FAILED if partial and sources and stats["sources_failed"] == len(sources) else
        (RunStatus.PARTIAL if partial else RunStatus.SUCCEEDED))
    session = db.get(DiscoverySession, session_id)
    session.status, session.finished_at, session.stats = status, utcnow(), stats
    finish_run(db, run, status, stats)
    RunRecorder(db, run).event("finished", f"Discovery finished: {status.value}", payload=stats)
    return session
