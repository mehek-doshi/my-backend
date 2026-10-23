"""Deduplication agent: same URL, same title fingerprint, or very similar title."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.types import Candidate
from app.core.textutil import jaccard, title_fingerprint, title_tokens, url_hash
from app.db.enums import TopicStatus
from app.db.models import SourceArticle, Topic
from app.services.app_settings import RuntimeSettings


class DeduplicationAgent:
    name = "deduplication"

    def check(self, db: Session, cand: Candidate, runtime: RuntimeSettings, *, exclude_topic_id: uuid.UUID | None = None) -> None:
        # 1. the exact same article already belongs to a topic
        if cand.url:
            hit = db.scalar(select(SourceArticle.topic_id).where(SourceArticle.url_hash == url_hash(cand.url)).limit(1))
            if hit is not None and hit != exclude_topic_id:
                cand.duplicate_of, cand.similarity = hit, 1.0
                return
        # 2. same title fingerprint, or a very similar set of title words
        fp, tokens = title_fingerprint(cand.title), title_tokens(cand.title)
        rows = db.execute(
            select(Topic.id, Topic.title, Topic.fingerprint)
            .where(Topic.status != TopicStatus.MERGED).limit(20000)
        ).all()
        best_id, best = None, 0.0
        for tid, title, fingerprint in rows:
            if tid == exclude_topic_id:
                continue
            sim = 1.0 if fingerprint == fp else jaccard(tokens, title_tokens(title))
            if sim > best:
                best_id, best = tid, sim
        cand.similarity = best
        if best_id is not None and best >= runtime.dedup_threshold:
            cand.duplicate_of = best_id
        elif best_id is not None and best >= runtime.dedup_review_threshold:
            cand.possible_duplicate_of = best_id
            cand.flags.append("possible_duplicate")
