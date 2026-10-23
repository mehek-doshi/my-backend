"""Notifications. The in-app row is always written. Email / Teams / Buddy rows are written as 'pending'
only when that integration is configured, and the worker delivers them (see worker/jobs.py).
A dedupe key makes every notification idempotent: reminders cannot be sent twice for the same event."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.enums import NotificationChannel as C
from app.db.enums import NotificationStatus as S
from app.db.models import Notification
from app.db.types import utcnow


def external_channels() -> list[C]:
    s = get_settings()
    out = []
    if s.mail_provider != "none":
        out.append(C.EMAIL)
    if s.teams_provider != "none":
        out.append(C.TEAMS)
    if s.buddy_provider != "none":
        out.append(C.BUDDY)
    return out


def notify(db: Session, user_id: uuid.UUID, kind: str, title: str, body: str = "", *, dedupe_key: str | None = None,
           payload: dict[str, Any] | None = None, external: bool = True) -> bool:
    """Returns False when this notification already exists (same dedupe key)."""
    channels = [C.IN_APP] + (external_channels() if external else [])
    created = False
    for ch in channels:
        if dedupe_key and db.scalar(select(Notification.id).where(Notification.user_id == user_id, Notification.channel == ch,
                                                                  Notification.dedupe_key == dedupe_key)):
            continue
        in_app = ch == C.IN_APP
        db.add(Notification(user_id=user_id, kind=kind, title=title[:300], body=body, payload=payload or {}, channel=ch,
                            status=S.SENT if in_app else S.PENDING, dedupe_key=dedupe_key, sent_at=utcnow() if in_app else None))
        created = created or in_app
    db.flush()
    return created
