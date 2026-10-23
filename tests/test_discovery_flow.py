"""Vertical slice: source -> discovery -> dedup/guardrails/verification -> automatic publication (Admin tools for the rest)."""
import uuid

from sqlalchemy import select

from app.db.enums import RunStatus, TopicStatus
from app.db.models import AgentEvent, Topic, TopicReview
from tests.conftest import FEED, PAGES, fake_transport  # noqa: F401

PUBLIC = (TopicStatus.OPEN_FOR_VOLUNTEERS, TopicStatus.IN_PROGRESS)

FEED_URL = "https://blog.example.com/feed.xml"


def add_source(client, admin, url=FEED_URL):
    r = client.post("/api/v1/sources", json={"name": "Example", "url": url}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def run_discovery(client, admin):
    r = client.post("/api/v1/discovery/sessions", headers=admin)
    assert r.status_code == 202, r.text
    return client.get(f"/api/v1/discovery/sessions/{r.json()['id']}", headers=admin).json()


def topics_by_title(db):
    return {t.title: t for t in db.scalars(select(Topic))}


def test_discovery_publishes_verified_topics_and_blocks_bad_ones(client, admin, services, db):
    add_source(client, admin)
    s = run_discovery(client, admin)
    assert s["status"] == "succeeded", s
    assert s["stats"]["candidates"] == 3 and s["stats"]["created"] == 3
    t = topics_by_title(db)
    agents = t["Building AI agents with MCP tool use"]
    assert agents.status == TopicStatus.OPEN_FOR_VOLUNTEERS and agents.verified is True and agents.category_id is not None
    assert t["Crypto agent token launch announced"].status == TopicStatus.BLOCKED
    assert s["stats"]["blocked"] == 1 and s["stats"]["open_for_volunteers"] + s["stats"]["pending_review"] == 2
    assert db.query(TopicReview).count() == 0  # nobody reviewed anything: publication was automatic
    assert any(l["action"] == "topic.auto_published" for l in client.get("/api/v1/admin/audit-logs?limit=50", headers=admin).json()["items"])


def test_verified_topic_without_category_or_with_possible_duplicate_waits_for_an_admin(client, admin, employee, services, db, make_topic):
    from app.core.textutil import title_fingerprint
    from app.agents.types import Candidate
    from app.services import topics as svc
    base = dict(title="Quantum widgets for everyone", url="https://blog.example.com/q", summary="A summary long enough.", verified=True,
                guardrail={"passed": True})
    no_cat = svc.persist_candidate(db, Candidate(**base, flags=["needs_category"]))
    assert no_cat.status == TopicStatus.PENDING_REVIEW
    cat = db.query(__import__("app.db.models", fromlist=["Category"]).Category).first()
    dup = svc.persist_candidate(db, Candidate(**{**base, "title": "Quantum widgets for all"}, category_id=cat.id, flags=["possible_duplicate"]))
    assert dup.status == TopicStatus.PENDING_REVIEW
    ok = svc.persist_candidate(db, Candidate(**{**base, "title": "Another fine subject"}, category_id=cat.id))
    assert ok.status == TopicStatus.OPEN_FOR_VOLUNTEERS
    unverified = svc.persist_candidate(db, Candidate(**{**base, "title": "Unverified subject here", "verified": False}, category_id=cat.id))
    assert unverified.status == TopicStatus.UNVERIFIED
    db.commit()
    shown = {x["title"] for x in client.get("/api/v1/topics", headers=employee).json()["items"]}
    assert shown == {"Another fine subject"}


def test_second_run_deduplicates(client, admin, services, db):
    add_source(client, admin)
    run_discovery(client, admin)
    s = run_discovery(client, admin)
    assert s["stats"]["duplicates"] == 3 and s["stats"]["created"] == 0
    assert db.query(Topic).count() == 3


def test_run_events_and_checkpoints_are_recorded(client, admin, services, db):
    add_source(client, admin)
    s = run_discovery(client, admin)
    events = list(db.scalars(select(AgentEvent).where(AgentEvent.run_id == uuid.UUID(s["agent_run_id"])).order_by(AgentEvent.seq)))
    assert events[0].event_type == "started" and events[-1].event_type == "finished"
    assert [e.seq for e in events] == list(range(1, len(events) + 1))


def test_failing_source_gives_partial_and_does_not_stop_others(client, admin, services, db):
    add_source(client, admin)
    add_source(client, admin, "https://broken.example.com/missing.xml")
    s = run_discovery(client, admin)
    assert s["status"] == "partial" and s["stats"]["sources_failed"] == 1 and s["stats"]["created"] == 3
    srcs = client.get("/api/v1/sources", headers=admin).json()["items"]
    broken = next(x for x in srcs if "broken" in x["url"])
    assert broken["consecutive_failures"] == 1 and broken["last_error"]


def test_employee_cannot_see_blocked_or_pending_topics_or_approve(client, admin, employee, services, db, make_topic):
    add_source(client, admin)
    run_discovery(client, admin)
    pending = make_topic("Waiting for an admin", status=TopicStatus.PENDING_REVIEW)
    published = sum(1 for t in db.scalars(select(Topic)) if t.status in PUBLIC)
    assert client.get("/api/v1/topics", headers=employee).json()["total"] == published > 0
    assert client.get(f"/api/v1/topics/{pending.id}", headers=employee).status_code == 404
    blocked = next(t for t in db.scalars(select(Topic)) if t.status == TopicStatus.BLOCKED)
    assert client.get(f"/api/v1/topics/{blocked.id}", headers=employee).status_code == 404
    assert client.post(f"/api/v1/topics/{pending.id}/approve", json={}, headers=employee).status_code == 403
    assert client.post("/api/v1/discovery/sessions", headers=employee).status_code == 403


def test_admin_approval_publishes_and_is_audited(client, admin, employee, db, make_topic):
    pending = make_topic("Waiting for an admin", status=TopicStatus.PENDING_REVIEW)
    r = client.post(f"/api/v1/topics/{pending.id}/approve", json={"comment": "good"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "open_for_volunteers"
    vis = client.get("/api/v1/topics", headers=employee).json()
    assert vis["total"] == 1 and "guardrail" not in vis["items"][0] and "relevance_score" not in vis["items"][0]
    assert db.query(TopicReview).count() == 1
    assert client.post(f"/api/v1/topics/{pending.id}/approve", json={}, headers=admin).status_code == 409


def test_blocked_and_unverified_topics_cannot_be_approved(client, admin, services, db, make_topic):
    add_source(client, admin)
    run_discovery(client, admin)
    blocked = next(t for t in db.scalars(select(Topic)) if t.status == TopicStatus.BLOCKED)
    r = client.post(f"/api/v1/topics/{blocked.id}/approve", json={}, headers=admin)
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"
    unverified = make_topic("Not verified yet", status=TopicStatus.UNVERIFIED, )
    unverified.verified = False
    db.commit()
    assert client.post(f"/api/v1/topics/{unverified.id}/approve", json={}, headers=admin).status_code == 409


def test_reject_and_merge(client, admin, db, make_topic):
    a, b, c = (make_topic(n, status=TopicStatus.PENDING_REVIEW) for n in ("Topic A here", "Topic B here", "Topic C here"))
    assert client.post(f"/api/v1/topics/{a.id}/reject", json={"reason": "not relevant"}, headers=admin).json()["status"] == "rejected"
    assert client.post(f"/api/v1/topics/{b.id}/merge", json={"target_topic_id": str(b.id)}, headers=admin).status_code == 409
    assert client.post(f"/api/v1/topics/{b.id}/merge", json={"target_topic_id": str(a.id)}, headers=admin).status_code == 409  # target rejected
    r = client.post(f"/api/v1/topics/{c.id}/merge", json={"target_topic_id": str(b.id)}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "merged" and r.json()["merged_into_id"] == str(b.id)


def test_custom_topic_with_a_verified_source_is_published(client, admin, employee, services):
    body = {"title": "Building AI agents with MCP tool use", "summary": "Agents using MCP tools for LLM workflows.",
            "source_url": "https://blog.example.com/agents-mcp"}
    r = client.post("/api/v1/topics/custom", json=body, headers=employee)
    assert r.status_code == 201 and r.json()["status"] == "open_for_volunteers"
    other = {"X-Dev-User": "other@neuleap.ai"}
    assert client.get("/api/v1/topics?mine=true", headers=employee).json()["total"] == 1
    assert client.get("/api/v1/topics", headers=other).json()["total"] == 1
    dup = client.post("/api/v1/topics/custom", json=body, headers=employee)
    assert dup.status_code == 409


def test_custom_topic_without_a_source_is_not_published(client, employee, services):
    r = client.post("/api/v1/topics/custom", json={"title": "Quilting patterns for beginners", "summary": "A hobby topic without any link."},
                    headers=employee)
    assert r.status_code == 201 and r.json()["status"] == "unverified"
    other = {"X-Dev-User": "other@neuleap.ai"}
    assert client.get("/api/v1/topics", headers=other).json()["total"] == 0
    assert client.get(f"/api/v1/topics/{r.json()['id']}", headers=other).status_code == 404


def test_custom_topic_with_internal_url_is_refused(client, employee, services):
    r = client.post("/api/v1/topics/custom", json={"title": "Internal thing here", "summary": "Some internal summary text.",
                                                   "source_url": "http://localhost/admin"}, headers=employee)
    assert r.status_code == 422


def test_source_with_internal_address_is_refused(client, admin):
    for url in ("http://localhost/feed", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/feed.xml"):
        r = client.post("/api/v1/sources", json={"name": "bad source", "url": url}, headers=admin)
        assert r.status_code == 422, url


def test_test_cases_only_on_open_topics(client, admin, employee, services, make_topic):
    pending = make_topic("Waiting for an admin", status=TopicStatus.PENDING_REVIEW)
    assert client.post(f"/api/v1/topics/{pending.id}/test-cases", json={"title": "Too early"}, headers=employee).status_code in (403, 404)
    add_source(client, admin)
    run_discovery(client, admin)
    open_topic = client.get("/api/v1/topics", headers=employee).json()["items"][0]
    r = client.post(f"/api/v1/topics/{open_topic['id']}/test-cases", json={"title": "Check tool calls"}, headers=employee)
    assert r.status_code == 201
    other = {"X-Dev-User": "other@neuleap.ai"}
    assert client.delete(f"/api/v1/topics/{open_topic['id']}/test-cases/{r.json()['id']}", headers=other).status_code == 403
    assert client.delete(f"/api/v1/topics/{open_topic['id']}/test-cases/{r.json()['id']}", headers=employee).status_code == 204
