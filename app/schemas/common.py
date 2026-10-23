from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class PageParams:
    def __init__(self, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=1_000_000)) -> None:
        self.limit, self.offset = limit, offset


def paginate(db: Session, stmt: Select, params: PageParams, *, count_stmt: Select | None = None) -> tuple[list, int]:
    total = db.scalar(count_stmt if count_stmt is not None else select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = list(db.scalars(stmt.limit(params.limit).offset(params.offset)))
    return rows, total


class Message(BaseModel):
    message: str


class UserOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    team: str | None = None
    job_title: str | None = None
    last_login_at: datetime | None = None
