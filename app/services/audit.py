"""Audit log: who did what, to what, when. Written in the same transaction as the action itself."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.context import client_ip_var, request_id_var
from app.db.models import AuditLog, User

_SENSITIVE = ("secret", "password", "token", "api_key", "authorization")


def _scrub(details: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in details.items():
        if any(s in k.lower() for s in _SENSITIVE):
            out[k] = "[redacted]"
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif isinstance(v, dict):
            out[k] = _scrub(v)
        else:
            out[k] = v
    return out


def audit(db: Session, actor: User | None, action: str, target_type: str, target_id: Any = None,
          details: dict[str, Any] | None = None) -> AuditLog:
    row = AuditLog(
        actor_id=actor.id if actor else None,
        actor_label=actor.email if actor else "system",
        action=action, target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=_scrub(details or {}), ip=client_ip_var.get(), request_id=request_id_var.get())
    db.add(row)
    return row
