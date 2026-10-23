"""Test configuration. Environment is set BEFORE the app is imported.

Default database is a temporary SQLite file. To run against PostgreSQL:
    $env:TEST_DATABASE_URL = "postgresql+psycopg://techradar:techradar@localhost:5432/techradar_test"
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="techradar-tests-")
_DB_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{Path(_TMP, 'test.db').as_posix()}"
if os.environ.get("TEST_DATABASE_URL") and not os.environ["TEST_DATABASE_URL"].split("?")[0].rstrip("/").endswith("_test"):
    raise SystemExit("TEST_DATABASE_URL must point at a database whose name ends in '_test': the tests DROP ALL TABLES in it.")
os.environ.update({
    "ENVIRONMENT": "test", "AUTH_MODE": "dev", "ALLOW_DEV_AUTH": "true", "DATABASE_URL": _DB_URL,
    "CELERY_TASK_ALWAYS_EAGER": "true", "LLM_PROVIDER": "mock", "SEARCH_PROVIDER": "none",
    "STORAGE_DIR": str(Path(_TMP, "storage")), "ALLOWED_EMAIL_DOMAINS": "neuleap.ai",
    "DIRECTORY_PROVIDER": "none", "MAIL_PROVIDER": "none", "TEAMS_PROVIDER": "none", "SHAREPOINT_PROVIDER": "none",
    "BUDDY_PROVIDER": "none", "CLIENT_NAME_DENYLIST": "AcmeCorp",
})

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.services import Services, set_services_factory  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.db.models  # noqa: E402,F401
from app.db.session import get_engine, new_session  # noqa: E402
from app.llm.providers import MockLLM  # noqa: E402
from app.search.providers import NullSearchProvider  # noqa: E402
from app.security.ssrf import SafeFetcher  # noqa: E402
from app.seed import seed_dev_users, seed_reference_data  # noqa: E402

FEED = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Building AI agents with MCP tool use</title><link>https://blog.example.com/agents-mcp</link>
<description>A practical guide to building agent workflows. Agents call tools through MCP. It covers LLM routing.</description></item>
<item><title>Fine-tuning small models with LoRA</title><link>https://blog.example.com/lora</link>
<description>Fine-tuning a small model with LoRA and quantization. Works for RAG pipelines too.</description></item>
<item><title>Crypto agent token launch announced</title><link>https://blog.example.com/crypto</link>
<description>Agent crypto funding round.</description></item>
</channel></rss>"""

PAGES = {
    "/agents-mcp": "<html><head><title>Building AI agents with MCP tool use</title></head><body><p>Building AI agents with MCP tool use. Agents call tools.</p></body></html>",
    "/lora": "<html><head><title>Fine-tuning small models with LoRA</title></head><body><p>Fine-tuning small models with LoRA.</p></body></html>",
    "/crypto": "<html><head><title>Crypto agent token launch announced</title></head><body><p>crypto</p></body></html>",
}


def fake_transport(feed: str = FEED, pages: dict | None = None, extra: dict | None = None) -> httpx.MockTransport:
    pages = {**PAGES, **(pages or {})}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/feed.xml":
            return httpx.Response(200, text=feed, headers={"content-type": "application/rss+xml"})
        if extra and path in extra:
            return extra[path](request)
        if path in pages:
            return httpx.Response(200, text=pages[path], headers={"content-type": "text/html; charset=utf-8"})
        return httpx.Response(404, text="nope", headers={"content-type": "text/html"})

    return httpx.MockTransport(handler)


def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


@pytest.fixture(autouse=True)
def no_real_dns(monkeypatch):
    import app.security.ssrf as ssrf
    monkeypatch.setattr(ssrf, "default_resolver", public_resolver)


@pytest.fixture(autouse=True)
def database():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = new_session()
    seed_reference_data(db)
    seed_dev_users(db)
    db.close()
    yield
    set_services_factory(None)


@pytest.fixture
def services():
    svc = Services(fetcher=SafeFetcher(resolver=public_resolver, transport=fake_transport()), llm=MockLLM(), search=NullSearchProvider())
    set_services_factory(lambda: svc)
    return svc


@pytest.fixture
def db():
    s = new_session()
    yield s
    s.close()


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def as_user(email: str, role: str | None = None) -> dict:
    h = {"X-Dev-User": email}
    if role:
        h["X-Dev-Role"] = role
    return h


@pytest.fixture
def admin():
    return as_user("admin@neuleap.ai")


@pytest.fixture
def reviewer():
    return as_user("reviewer@neuleap.ai")


@pytest.fixture
def employee():
    return as_user("employee@neuleap.ai")


@pytest.fixture
def make_topic(db):
    from app.db.enums import TopicStatus
    from app.db.models import Category, Topic
    from app.core.textutil import title_fingerprint

    def make(title="Agent evaluation harness", status=TopicStatus.OPEN_FOR_VOLUNTEERS, **kw):
        cat = db.query(Category).first()
        t = Topic(title=title, summary="Summary of the topic.", category_id=cat.id, status=status, verified=True,
                  guardrail={"passed": True}, fingerprint=title_fingerprint(title), **kw)
        db.add(t)
        db.commit()
        return t
    return make


def make_user_with_role(db, email, role="Employee"):
    from app.db.enums import Role
    from app.db.models import User
    u = db.query(User).filter(User.email == email).first()
    if not u:
        u = User(email=email, display_name=email.split("@")[0], role=Role(role))
        db.add(u)
        db.commit()
    return u


def file_part(name="notes.md", content=b"# My findings\nAll good.\n"):
    return {"file": (name, content, "application/octet-stream")}


def submit(client, headers, files=None, **data):
    body = {"title": "Agent harness POC", "summary": "What I built", "type": "poc"}
    body.update(data)
    return client.post("/api/v1/artifacts", data=body, files=files, headers=headers)


@pytest.fixture
def integrations():
    from app.integrations import null_mock as nm
    from app.integrations.registry import Integrations, set_integrations_factory
    integ = Integrations(directory=nm.MockDirectory(), mail=nm.MockMail(), teams=nm.MockTeams(), sharepoint=nm.MockSharePoint(), buddy=nm.MockBuddy())
    set_integrations_factory(lambda: integ)
    yield integ
    set_integrations_factory(None)
