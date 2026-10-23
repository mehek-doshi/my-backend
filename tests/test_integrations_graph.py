"""Graph / Teams clients against MOCKED HTTP transports. Not a test against a real tenant."""
import json

import httpx
import pytest

from app.core.config import Settings
from app.integrations.base import IntegrationError, NotConfigured
from app.integrations.graph import GraphClient, GraphDirectory, GraphMail, GraphSharePoint, TeamsWebhook
from app.integrations.registry import build_integrations


def settings(**kw):
    base = dict(_env_file=None, environment="test", auth_mode="entra", graph_tenant_id="t", graph_client_id="c",
                graph_client_secret="s", mail_sender="radar@neuleap.ai", sharepoint_drive_id="drive1")
    base.update(kw)
    return Settings(**base)


def transport(routes, log=None):
    def handler(req: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append((req.method, str(req.url), req.headers.get("authorization"), req.content))
        if "oauth2/v2.0/token" in str(req.url):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        for needle, resp in routes.items():
            if needle in str(req.url):
                return resp(req) if callable(resp) else resp
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_directory_pages_and_skips_users_without_email():
    page1 = {"value": [{"id": "1", "displayName": "A", "mail": "A@neuleap.ai", "accountEnabled": True},
                       {"id": "2", "displayName": "NoMail"}], "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?page=2"}
    page2 = {"value": [{"id": "3", "displayName": "C", "userPrincipalName": "c@neuleap.ai", "accountEnabled": False}]}

    def users(req):
        return httpx.Response(200, json=page2 if "page=2" in str(req.url) else page1)

    log = []
    d = GraphDirectory(GraphClient(settings(), transport({"/users": users}, log)))
    out = d.list_users()
    assert [(u.email, u.enabled) for u in out] == [("a@neuleap.ai", True), ("c@neuleap.ai", False)]
    assert all(h == "Bearer tok" for _, url, h, _ in log if "/users" in url)


def test_mail_send_payload():
    log = []
    GraphMail(GraphClient(settings(), transport({"/sendMail": httpx.Response(202)}, log)), "radar@neuleap.ai").send("a@neuleap.ai", "Hi", "Body")
    body = json.loads(next(c for m, u, _, c in log if "sendMail" in u))
    assert body["message"]["toRecipients"][0]["emailAddress"]["address"] == "a@neuleap.ai" and body["saveToSentItems"] is False


def test_graph_errors_become_integration_errors():
    c = GraphClient(settings(), transport({"/sendMail": httpx.Response(403)}))
    with pytest.raises(IntegrationError):
        GraphMail(c, "radar@neuleap.ai").send("a@neuleap.ai", "s", "b")
    bad = httpx.MockTransport(lambda r: httpx.Response(401))
    with pytest.raises(IntegrationError):
        GraphClient(settings(), bad).token()


def test_graph_retries_on_throttling(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def flaky(req):
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}) if calls["n"] < 3 else httpx.Response(202)

    GraphMail(GraphClient(settings(), transport({"/sendMail": flaky})), "x@neuleap.ai").send("a@neuleap.ai", "s", "b")
    assert calls["n"] == 3


def test_sharepoint_simple_and_session_upload(tmp_path):
    small = tmp_path / "a.md"; small.write_bytes(b"hello")
    log = []
    sp = GraphSharePoint(GraphClient(settings(), transport({"/content": httpx.Response(201, json={"id": "ITEM1"})}, log)), "drive1")
    assert sp.upload(small, "Tech Radar/Topic one", "a.md") == "ITEM1"
    assert any("Tech%20Radar/Topic%20one/a.md" in u for _, u, _, _ in log)

    big = tmp_path / "big.zip"; big.write_bytes(b"x" * (5 * 1024 * 1024))
    ranges = []

    def put(req):
        ranges.append(req.headers["content-range"])
        return httpx.Response(201, json={"id": "BIG"}) if len(ranges) == 2 else httpx.Response(202, json={})

    routes = {"createUploadSession": httpx.Response(200, json={"uploadUrl": "https://upload.example.com/s1"}), "upload.example.com": put}
    sp2 = GraphSharePoint(GraphClient(settings(), transport(routes)), "drive1")
    assert sp2.upload(big, "F", "big.zip") == "BIG"
    assert ranges[0].startswith("bytes 0-") and ranges[1].endswith(f"/{5 * 1024 * 1024}")


def test_teams_webhook():
    got = []
    t = TeamsWebhook("https://example.webhook.office.com/x", httpx.MockTransport(lambda r: got.append(json.loads(r.content)) or httpx.Response(200)))
    t.post("Title", "Text")
    assert "Title" in got[0]["text"]
    with pytest.raises(NotConfigured):
        TeamsWebhook("http://insecure.example.com/x")
    with pytest.raises(IntegrationError):
        TeamsWebhook("https://example.webhook.office.com/x", httpx.MockTransport(lambda r: httpx.Response(500))).post("a", "b")


def test_registry_reports_unconfigured_and_never_claims_live_verification():
    integ = build_integrations(settings(directory_provider="graph", mail_provider="graph", sharepoint_provider="graph"),
                               transport({}))
    st = integ.status()
    assert st["directory"]["provider"] == "graph" and st["teams"]["configured"] is False and st["buddy"]["provider"] == "none"
    assert all(v["verified_against_live_system"] is False for v in st.values())
    missing = build_integrations(settings(graph_client_secret="", directory_provider="graph"))
    assert missing.directory.name == "none" and "GRAPH_CLIENT_SECRET" in missing.errors["directory"]
    nomail = build_integrations(settings(mail_provider="graph", mail_sender=""), transport({}))
    assert nomail.mail.name == "none" and "MAIL_SENDER" in nomail.errors["mail"]
