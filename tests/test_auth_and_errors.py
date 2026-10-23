import pytest

from app.core.config import Settings


def test_health_and_ready(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/ready").json() == {"status": "ready"}


def test_auth_required_and_error_shape(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    err = r.json()["error"]
    assert err["code"] == "unauthorized" and err["request_id"] and r.headers["X-Request-ID"] == err["request_id"]


def test_me_provisions_employee(client):
    r = client.get("/api/v1/auth/me", headers={"X-Dev-User": "new.person@neuleap.ai"})
    assert r.status_code == 200 and r.json()["role"] == "Employee"


def test_dev_user_must_have_allowed_domain(client):
    assert client.get("/api/v1/auth/me", headers={"X-Dev-User": "x@evil.com"}).status_code == 401


def test_validation_error_does_not_echo_values(client, admin):
    r = client.post("/api/v1/sources", json={"name": "x", "url": "not-a-url-SECRET123"}, headers=admin)
    assert r.status_code == 422 and "SECRET123" not in r.text


def test_pagination_limits(client, admin):
    assert client.get("/api/v1/topics?limit=1000", headers=admin).status_code == 422
    assert client.get("/api/v1/topics?limit=5&offset=0", headers=admin).json()["limit"] == 5


def _prod(**kw):
    base = dict(_env_file=None, environment="production", auth_mode="entra", allow_dev_auth=False, entra_tenant_id="t",
                entra_client_id="c", llm_provider="openai_compatible", search_provider="none", directory_provider="none",
                mail_provider="none", teams_provider="none", sharepoint_provider="none", buddy_provider="none",
                celery_task_always_eager=False)
    base.update(kw)
    return Settings(**base)


def test_production_refuses_unsafe_configuration():
    assert not _prod().dev_auth_active
    for bad in ({"auth_mode": "dev", "allow_dev_auth": True}, {"allow_dev_auth": True}, {"llm_provider": "mock"},
                {"entra_tenant_id": ""}, {"celery_task_always_eager": True}, {"directory_provider": "mock"}):
        with pytest.raises(ValueError):
            _prod(**bad)


def test_dev_mode_needs_both_switches():
    with pytest.raises(ValueError):
        Settings(_env_file=None, environment="development", auth_mode="dev", allow_dev_auth=False)
    assert Settings(_env_file=None, environment="development", auth_mode="dev", allow_dev_auth=True).dev_auth_active


def test_dev_header_ignored_when_dev_mode_off(client, monkeypatch):
    from app.core.config import get_settings
    s = get_settings()
    monkeypatch.setattr(type(s), "dev_auth_active", property(lambda self: False))
    r = client.get("/api/v1/auth/me", headers={"X-Dev-User": "admin@neuleap.ai"})
    assert r.status_code == 401
