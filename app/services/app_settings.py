"""Admin-editable runtime settings stored in the database, with validated defaults."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppSetting, User


class RuntimeSettings(BaseModel):
    """Full set of runtime settings with their defaults."""

    model_config = ConfigDict(extra="forbid")

    include_keywords: list[str] = Field(default_factory=lambda: ["agent", "LLM", "RAG", "fine-tuning"])
    exclude_keywords: list[str] = Field(default_factory=lambda: ["crypto", "hiring", "funding"])
    dedup_threshold: float = Field(0.6, gt=0, le=1)          # at or above: same topic
    dedup_review_threshold: float = Field(0.45, gt=0, le=1)  # at or above: flag "possible duplicate"
    min_verified_sources: int = Field(1, ge=1, le=10)
    max_volunteers: int = Field(5, ge=1, le=50)
    invitation_expiry_days: int = Field(7, ge=1, le=60)
    reminder_dedupe_hours: int = Field(24, ge=1, le=168)
    due_soon_hours: int = Field(24, ge=1, le=240)
    stage_days_study: int = Field(14, ge=1, le=120)
    stage_days_poc: int = Field(14, ge=1, le=120)
    stage_days_presentation: int = Field(7, ge=1, le=120)

    @field_validator("include_keywords", "exclude_keywords")
    @classmethod
    def _clean_keywords(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for k in v:
            k = k.strip()
            if not k or len(k) > 60:
                raise ValueError("keywords must be 1-60 characters")
            if k.lower() not in [o.lower() for o in out]:
                out.append(k)
        if len(out) > 100:
            raise ValueError("too many keywords")
        return out


class RuntimeSettingsUpdate(BaseModel):
    """Partial update: only the fields that are sent change."""

    model_config = ConfigDict(extra="forbid")

    include_keywords: list[str] | None = None
    exclude_keywords: list[str] | None = None
    dedup_threshold: float | None = Field(None, gt=0, le=1)
    dedup_review_threshold: float | None = Field(None, gt=0, le=1)
    min_verified_sources: int | None = Field(None, ge=1, le=10)
    max_volunteers: int | None = Field(None, ge=1, le=50)
    invitation_expiry_days: int | None = Field(None, ge=1, le=60)
    reminder_dedupe_hours: int | None = Field(None, ge=1, le=168)
    due_soon_hours: int | None = Field(None, ge=1, le=240)
    stage_days_study: int | None = Field(None, ge=1, le=120)
    stage_days_poc: int | None = Field(None, ge=1, le=120)
    stage_days_presentation: int | None = Field(None, ge=1, le=120)


def load_settings(db: Session) -> RuntimeSettings:
    stored = {r.key: r.value for r in db.scalars(select(AppSetting))}
    known = {k: v for k, v in stored.items() if k in RuntimeSettings.model_fields}
    return RuntimeSettings.model_validate(known)


def update_settings(db: Session, update: RuntimeSettingsUpdate, actor: User | None) -> tuple[RuntimeSettings, dict[str, Any]]:
    changes = update.model_dump(exclude_unset=True, exclude_none=True)
    current = load_settings(db)
    merged = RuntimeSettings.model_validate({**current.model_dump(), **changes})  # re-validates keyword lists
    if merged.dedup_review_threshold > merged.dedup_threshold:
        raise ValueError("dedup_review_threshold must not exceed dedup_threshold")
    for key in changes:
        value = getattr(merged, key)
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value, updated_by=actor.id if actor else None))
        else:
            row.value, row.updated_by = value, actor.id if actor else None
    return merged, {k: getattr(merged, k) for k in changes}


def stage_days(s: RuntimeSettings) -> dict[str, int]:
    return {"Study": s.stage_days_study, "POC": s.stage_days_poc, "Presentation": s.stage_days_presentation}
