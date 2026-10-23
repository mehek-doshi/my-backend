"""Users, categories, technology sources."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.enums import Role, SourceKind
from app.db.types import UTCDateTime, enum_col


class User(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("entra_object_id", name="uq_users_entra_object_id"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        Index("ix_users_role", "role"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    entra_object_id: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[Role] = mapped_column(enum_col(Role, "user_role"), nullable=False, default=Role.EMPLOYEE)
    team: Mapped[str | None] = mapped_column(String(100))
    job_title: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Category(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("name", name="uq_categories_name"),
        UniqueConstraint("slug", name="uq_categories_slug"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    retired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TechnologySource(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "technology_sources"
    __table_args__ = (
        UniqueConstraint("url", name="uq_technology_sources_url"),
        CheckConstraint("consecutive_failures >= 0", name="failures_non_negative"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    kind: Mapped[SourceKind] = mapped_column(enum_col(SourceKind, "source_kind"), nullable=False, default=SourceKind.FEED)
    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("categories.id", ondelete="SET NULL"))
    last_crawled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
