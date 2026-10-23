"""Request dependencies: DB session, current user and role checks."""
from __future__ import annotations

from typing import Annotated, Callable

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import Forbidden
from app.core.security import EntraValidator, authenticate
from app.db.enums import Role
from app.db.models import User
from app.db.session import get_db

DB = Annotated[Session, Depends(get_db)]

_validator: EntraValidator | None = None


def get_validator() -> EntraValidator | None:
    """Overridable in tests (injects a local JWKS)."""
    return _validator


def set_validator(v: EntraValidator | None) -> None:
    global _validator
    _validator = v


def current_user(
    db: DB,
    authorization: Annotated[str | None, Header()] = None,
    x_dev_user: Annotated[str | None, Header()] = None,
    x_dev_role: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
    validator: EntraValidator | None = Depends(get_validator),
) -> User:
    return authenticate(authorization, x_dev_user, x_dev_role, db, settings, validator)


CurrentUser = Annotated[User, Depends(current_user)]


def require_roles(*roles: Role) -> Callable[..., User]:
    allowed = set(roles)

    def dep(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise Forbidden("You do not have permission to do this")
        return user

    return dep


AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]
ReviewerUser = AdminUser  # Moderator was merged into Admin
