"""Authentication.

* Production: Microsoft Entra ID access tokens (RS256) validated against the tenant's JWKS.
  Checks: signature, expiry, audience, issuer, tenant id, allowed e-mail domain. The DB role is
  overwritten from the token's app roles at every login, so removing a role in Entra takes effect.
* Development only: `X-Dev-User: someone@neuleap.ai` header. Needs AUTH_MODE=dev AND ALLOW_DEV_AUTH=true
  AND ENVIRONMENT != production (Settings refuses to start otherwise).
"""
from __future__ import annotations

import time
from typing import Any, Callable

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import Forbidden, ServiceUnavailable, Unauthorized
from app.db.enums import Role
from app.db.models import User
from app.db.types import utcnow
from app.services.audit import audit

JWKSProvider = Callable[[], dict[str, Any]]


class EntraValidator:
    def __init__(self, settings: Settings, jwks_provider: JWKSProvider | None = None) -> None:
        self.s = settings
        self._jwks_provider = jwks_provider
        self._cache: tuple[float, dict[str, Any]] | None = None

    @property
    def issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.s.entra_tenant_id}/v2.0"

    @property
    def audiences(self) -> list[str]:
        client = self.s.entra_client_id
        return [a for a in (self.s.entra_audience, client, f"api://{client}" if client else "") if a]

    def _jwks(self, force: bool = False) -> dict[str, Any]:
        if self._jwks_provider:
            return self._jwks_provider()
        if self._cache and not force and time.time() - self._cache[0] < 3600:
            return self._cache[1]
        url = f"https://login.microsoftonline.com/{self.s.entra_tenant_id}/discovery/v2.0/keys"
        try:
            data = httpx.get(url, timeout=5).raise_for_status().json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceUnavailable("Could not reach the sign-in service to check your token") from exc
        self._cache = (time.time(), data)
        return data

    def validate(self, token: str) -> dict[str, Any]:
        if not self.s.entra_tenant_id or not self.s.entra_client_id:
            raise ServiceUnavailable("Single sign-on is not configured on this server")
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as exc:
            raise Unauthorized("Invalid token") from exc
        key = None
        for attempt in (False, True):
            for jwk in self._jwks(force=attempt).get("keys", []):
                if jwk.get("kid") == kid:
                    key = jwt.PyJWK(jwk).key
                    break
            if key is not None or self._jwks_provider:
                break
        if key is None:
            raise Unauthorized("Invalid token")
        try:
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.audiences, issuer=self.issuer,
                                options={"require": ["exp", "iss", "aud"]}, leeway=30)
        except jwt.PyJWTError as exc:
            raise Unauthorized("Invalid or expired token") from exc
        if claims.get("tid") != self.s.entra_tenant_id:
            raise Unauthorized("Token is from a different tenant")
        return claims

    def role_from(self, claims: dict[str, Any]) -> Role:
        roles = set(claims.get("roles") or [])
        if self.s.entra_admin_role in roles:
            return Role.ADMIN
        if self.s.entra_moderator_role and self.s.entra_moderator_role in roles:
            return Role.ADMIN  # Moderator was merged into Admin; old Moderator assignments keep their access
        return Role.EMPLOYEE


def _email_ok(email: str, settings: Settings) -> bool:
    domains = settings.allowed_email_domain_list
    return not domains or email.rsplit("@", 1)[-1].lower() in domains


def _provision(db: Session, *, email: str, name: str, oid: str | None, role: Role | None) -> User:
    user = (db.scalar(select(User).where(User.entra_object_id == oid)) if oid else None) or \
        db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, display_name=name or email.split("@")[0], entra_object_id=oid, role=role or Role.EMPLOYEE)
        db.add(user)
        db.flush()
        audit(db, user, "user.provisioned", "user", user.id, {"role": user.role.value})
    else:
        if oid and not user.entra_object_id:
            user.entra_object_id = oid
        if name:
            user.display_name = name
        if role is not None and role != user.role:
            audit(db, user, "user.role_synced", "user", user.id, {"from": user.role.value, "to": role.value})
            user.role = role
    user.last_login_at = utcnow()
    db.commit()
    return user


def authenticate(authorization: str | None, dev_user: str | None, dev_role: str | None, db: Session,
                 settings: Settings, validator: EntraValidator | None) -> User:
    if settings.dev_auth_active:
        if not dev_user:
            raise Unauthorized("Development mode: send the X-Dev-User header")
        email = dev_user.strip().lower()
        if "@" not in email or not _email_ok(email, settings):
            raise Unauthorized("Development user e-mail is not allowed")
        role = None
        if dev_role:
            try:
                role = Role(dev_role)
                if role == Role.MODERATOR:
                    role = Role.ADMIN
            except ValueError as exc:
                raise Unauthorized("Unknown X-Dev-Role") from exc
        existing = db.scalar(select(User).where(User.email == email))
        user = existing or _provision(db, email=email, name=email.split("@")[0], oid=None, role=role)
        if existing and role and role != existing.role:
            existing.role = role
            db.commit()
        if not user.is_active:
            raise Forbidden("This account is disabled")
        return user
    # production path: bearer token only; dev headers are ignored
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized("Missing bearer token")
    validator = validator or EntraValidator(settings)
    claims = validator.validate(authorization[7:].strip())
    email = str(claims.get("preferred_username") or claims.get("email") or claims.get("upn") or "").strip().lower()
    if "@" not in email:
        raise Unauthorized("Token has no e-mail address")
    if not _email_ok(email, settings):
        raise Forbidden("Your e-mail domain is not allowed")
    user = _provision(db, email=email, name=str(claims.get("name") or ""), oid=claims.get("oid"), role=validator.role_from(claims))
    if not user.is_active:
        raise Forbidden("This account is disabled")
    return user
