import pytest

from tests.conftest import as_user, file_part, submit

ADMIN_ONLY = [("get", "/api/v1/admin/audit-logs"), ("get", "/api/v1/admin/agent-runs"), ("get", "/api/v1/admin/settings"),
              ("get", "/api/v1/admin/users"), ("get", "/api/v1/admin/jobs"), ("get", "/api/v1/sources"),
              ("get", "/api/v1/discovery/sessions")]


@pytest.mark.parametrize("method,url", ADMIN_ONLY)
def test_admin_only_endpoints(client, employee, admin, method, url):
    assert getattr(client, method)(url, headers=employee).status_code == 403
    assert getattr(client, method)(url, headers=admin).status_code == 200
    assert getattr(client, method)(url).status_code == 401


def test_dashboard_visible_to_admin_not_employee(client, employee, admin):
    assert client.get("/api/v1/admin/dashboard", headers=employee).status_code == 403
    d = client.get("/api/v1/admin/dashboard", headers=admin).json()
    assert "awaiting_topic_review" in d and "overdue_assignments" in d


def test_audit_log_records_admin_actions_without_secrets(client, admin, employee, reviewer):
    client.post("/api/v1/categories", json={"name": "Quantum"}, headers=admin)
    a = submit(client, employee, file_part()).json()
    client.post(f"/api/v1/artifacts/{a['id']}/approve", json={"comment": "ok"}, headers=reviewer)
    logs = client.get("/api/v1/admin/audit-logs?limit=100", headers=admin).json()["items"]
    actions = {l["action"] for l in logs}
    assert {"category.create", "artifact.submit", "artifact.scanned", "artifact.approved"} <= actions
    approved = next(l for l in logs if l["action"] == "artifact.approved")
    assert approved["actor_label"] == "reviewer@neuleap.ai" and approved["request_id"]
    only = client.get("/api/v1/admin/audit-logs?action=category.create", headers=admin).json()
    assert only["total"] == 1


def test_categories_admin_only_and_unique(client, admin, employee):
    assert client.post("/api/v1/categories", json={"name": "New one"}, headers=employee).status_code == 403
    assert client.post("/api/v1/categories", json={"name": "Agentic AI"}, headers=admin).status_code == 409
    cats = client.get("/api/v1/categories", headers=employee).json()
    assert len(cats) == 4
    cid = cats[0]["id"]
    assert client.patch(f"/api/v1/categories/{cid}", json={"retired": True}, headers=admin).json()["retired"] is True
    assert len(client.get("/api/v1/categories", headers=employee).json()) == 3


def test_settings_patch_validates_and_audits(client, admin):
    r = client.patch("/api/v1/admin/settings", json={"max_volunteers": 8, "exclude_keywords": ["crypto", "gossip"]}, headers=admin)
    assert r.status_code == 200 and r.json()["max_volunteers"] == 8
    assert client.get("/api/v1/admin/settings", headers=admin).json()["exclude_keywords"] == ["crypto", "gossip"]
    assert client.patch("/api/v1/admin/settings", json={"max_volunteers": 500}, headers=admin).status_code == 422
    assert client.patch("/api/v1/admin/settings", json={"min_relevance": 85}, headers=admin).status_code == 422  # removed setting
    assert client.patch("/api/v1/admin/settings", json={"unknown": 1}, headers=admin).status_code == 422
    assert client.patch("/api/v1/admin/settings", json={"dedup_threshold": 0.2}, headers=admin).status_code == 422
    assert client.get("/api/v1/admin/audit-logs?action=settings.update", headers=admin).json()["total"] == 1


def test_user_management(client, admin, employee):
    me = client.get("/api/v1/auth/me", headers=admin).json()
    assert client.patch(f"/api/v1/admin/users/{me['id']}", json={"is_active": False}, headers=admin).status_code == 409
    emp = client.get("/api/v1/auth/me", headers=employee).json()
    assert client.patch(f"/api/v1/admin/users/{emp['id']}", json={"role": "Admin"}, headers=admin).json()["role"] == "Admin"
    assert client.patch(f"/api/v1/admin/users/{emp['id']}", json={"role": "Moderator"}, headers=admin).status_code == 422  # role was merged into Admin
    assert client.patch(f"/api/v1/admin/users/{emp['id']}", json={"is_active": False}, headers=admin).status_code == 200
    assert client.get("/api/v1/auth/me", headers=employee).status_code == 403  # disabled accounts are locked out
    assert client.patch(f"/api/v1/admin/users/{emp['id']}", json={"role": "Superuser"}, headers=admin).status_code == 422
    assert client.patch(f"/api/v1/admin/users/{emp['id']}", json={"is_active": False}, headers=employee).status_code in (403,)


def test_agent_run_progress_endpoint(client, admin, services):
    client.post("/api/v1/sources", json={"name": "Example", "url": "https://blog.example.com/feed.xml"}, headers=admin)
    s = client.post("/api/v1/discovery/sessions", headers=admin).json()
    runs = client.get("/api/v1/admin/agent-runs?workflow=discovery", headers=admin).json()
    assert runs["total"] == 1 and runs["items"][0]["status"] == "succeeded"
    ev = client.get(f"/api/v1/admin/agent-runs/{s['agent_run_id']}/events", headers=admin).json()
    assert ev[0]["event_type"] == "started"
    later = client.get(f"/api/v1/admin/agent-runs/{s['agent_run_id']}/events?after_seq={ev[-1]['seq'] - 1}", headers=admin).json()
    assert len(later) == 1 and later[0]["event_type"] == "finished"
    assert client.get("/api/v1/admin/agent-runs/00000000-0000-0000-0000-000000000000", headers=admin).status_code == 404
