"""Entra ID token validation, tested against a locally generated key pair (no network, no real tenant)."""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.core.errors import Forbidden, ServiceUnavailable, Unauthorized
from app.core.security import EntraValidator, authenticate
from app.db.enums import Role
from app.db.models import User

TENANT, CLIENT = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def settings(**kw):
    base = dict(_env_file=None, environment="production", auth_mode="entra", allow_dev_auth=False, entra_tenant_id=TENANT,
                entra_client_id=CLIENT, llm_provider="openai_compatible", search_provider="none", directory_provider="none",
                mail_provider="none", teams_provider="none", sharepoint_provider="none", buddy_provider="none",
                celery_task_always_eager=False, allowed_email_domains="neuleap.ai")
    base.update(kw)
    return Settings(**base)


def jwks():
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
    jwk.update(kid="k1", use="sig", alg="RS256")
    return {"keys": [jwk]}


def token(key=KEY, **over):
    claims = {"iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": CLIENT, "tid": TENANT, "oid": "oid-1",
              "preferred_username": "Jane.Doe@neuleap.ai", "name": "Jane Doe", "exp": int(time.time()) + 600, "roles": []}
    claims.update(over)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256", headers={"kid": "k1"})


def auth(tok, db, **kw):
    s = settings(**kw)
    return authenticate(f"Bearer {tok}", None, None, db, s, EntraValidator(s, jwks_provider=jwks))


def test_valid_token_provisions_user(db):
    u = auth(token(), db)
    assert u.email == "jane.doe@neuleap.ai" and u.role == Role.EMPLOYEE and u.entra_object_id == "oid-1"
    assert auth(token(), db).id == u.id
    assert db.query(User).filter(User.email == "jane.doe@neuleap.ai").count() == 1


def test_roles_map_and_are_resynced_every_login(db):
    assert auth(token(roles=["TechRadar.Admin"]), db).role == Role.ADMIN
    assert auth(token(roles=["TechRadar.Moderator"]), db).role == Role.ADMIN  # old Moderators keep access as Admins
    assert auth(token(roles=[]), db).role == Role.EMPLOYEE  # removing the role in Entra removes the access


@pytest.mark.parametrize("over,exc", [
    ({"exp": int(time.time()) - 3600}, Unauthorized), ({"aud": "someone-else"}, Unauthorized),
    ({"iss": "https://evil.example.com/"}, Unauthorized), ({"tid": "other-tenant"}, Unauthorized),
    ({"preferred_username": "x@evil.com"}, Forbidden), ({"preferred_username": "no-at-sign"}, Unauthorized),
])
def test_bad_tokens_rejected(db, over, exc):
    with pytest.raises(exc):
        auth(token(**over), db)


def test_wrong_signature_and_alg_none_rejected(db):
    with pytest.raises(Unauthorized):
        auth(token(key=OTHER), db)
    with pytest.raises(Unauthorized):
        auth(jwt.encode({"aud": CLIENT, "exp": int(time.time()) + 60}, key=None, algorithm="none", headers={"kid": "k1"}), db)
    with pytest.raises(Unauthorized):
        auth("garbage", db)


def test_missing_bearer_and_dev_header_ignored_in_production(db):
    s = settings()
    with pytest.raises(Unauthorized):
        authenticate(None, "admin@neuleap.ai", "Admin", db, s, EntraValidator(s, jwks_provider=jwks))


def test_disabled_user_is_refused(db):
    u = auth(token(), db)
    u.is_active = False
    db.commit()
    with pytest.raises(Forbidden):
        auth(token(), db)


def test_unconfigured_entra_fails_closed(db):
    s = Settings(_env_file=None, environment="development", auth_mode="entra", allow_dev_auth=False)
    with pytest.raises(ServiceUnavailable):
        authenticate("Bearer " + token(), None, None, db, s, EntraValidator(s, jwks_provider=jwks))
