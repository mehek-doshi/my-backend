import uuid
from datetime import timedelta

from app.db.enums import AssignmentStatus, InvitationStatus, TopicStatus, VolunteerStatus
from app.db.models import Assignment, Invitation, Volunteer
from app.db.types import utcnow
from tests.conftest import as_user, file_part, make_user_with_role, submit

EMP = "employee@neuleap.ai"


def invite(client, admin, topic, *emails):
    return client.post(f"/api/v1/topics/{topic.id}/invitations", json={"emails": list(emails)}, headers=admin)


def test_invitation_accept_creates_volunteer_and_study_assignment(client, admin, employee, make_topic, db):
    t = make_topic()
    r = invite(client, admin, t, EMP)
    assert r.status_code == 201 and len(r.json()) == 1
    mine = client.get("/api/v1/invitations/mine", headers=employee).json()
    assert mine[0]["topic_title"] == t.title
    other = as_user("other@neuleap.ai")
    assert client.post(f"/api/v1/invitations/{mine[0]['id']}/accept", headers=other).status_code == 404
    acc = client.post(f"/api/v1/invitations/{mine[0]['id']}/accept", headers=employee)
    assert acc.status_code == 200 and acc.json()["volunteer"]["status"] == "active"
    a = client.get("/api/v1/me/assignments", headers=employee).json()
    assert len(a) == 1 and a[0]["stage"] == "Study" and a[0]["status"] == "open"
    db.expire_all()
    assert db.get(type(t), t.id).status == TopicStatus.IN_PROGRESS
    assert client.post(f"/api/v1/invitations/{mine[0]['id']}/accept", headers=employee).status_code == 409
    assert invite(client, admin, t, EMP).json() == []  # idempotent: already in


def test_decline_expire_revoke(client, admin, employee, make_topic, db):
    t = make_topic()
    inv = invite(client, admin, t, EMP).json()[0]
    assert client.post(f"/api/v1/invitations/{inv['id']}/decline", headers=employee).json()["status"] == "declined"
    inv2 = invite(client, admin, t, EMP).json()[0]  # declined invitations can be re-issued
    row = db.get(Invitation, uuid.UUID(inv2["id"]))
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert client.post(f"/api/v1/invitations/{inv2['id']}/accept", headers=employee).status_code == 410
    inv3 = invite(client, admin, t, EMP).json()[0]
    assert client.post(f"/api/v1/invitations/{inv3['id']}/revoke", headers=admin).json()["status"] == "revoked"
    assert client.post(f"/api/v1/invitations/{inv3['id']}/accept", headers=employee).status_code == 409


def test_only_admin_can_invite_and_topic_must_be_open(client, admin, employee, make_topic):
    t = make_topic()
    assert client.post(f"/api/v1/topics/{t.id}/invitations", json={"emails": [EMP]}, headers=employee).status_code == 403
    closed = make_topic("Closed one", status=TopicStatus.PENDING_REVIEW)
    assert invite(client, admin, closed, EMP).status_code == 409
    assert invite(client, admin, t, "nobody@neuleap.ai").status_code == 422


def test_self_join_requires_open_topic(client, employee, make_topic):
    pending = make_topic("Pending", status=TopicStatus.PENDING_REVIEW)
    assert client.post(f"/api/v1/topics/{pending.id}/volunteer", headers=employee).status_code == 404
    t = make_topic()
    assert client.post(f"/api/v1/topics/{t.id}/volunteer", headers=employee).status_code == 201
    assert client.post(f"/api/v1/topics/{t.id}/volunteer", headers=employee).status_code == 409


def test_capacity_waitlist_and_promotion(client, make_topic, db):
    t = make_topic(max_volunteers=1)
    a, b = as_user("a@neuleap.ai"), as_user("b@neuleap.ai")
    assert client.post(f"/api/v1/topics/{t.id}/volunteer", headers=a).json()["status"] == "active"
    rb = client.post(f"/api/v1/topics/{t.id}/volunteer", headers=b)
    assert rb.json()["status"] == "waitlisted"
    assert client.get("/api/v1/me/assignments", headers=b).json() == []
    assert client.delete(f"/api/v1/topics/{t.id}/volunteer", headers=a).status_code == 204
    assert client.get("/api/v1/me/volunteering", headers=b).json()[0]["status"] == "active"
    assert client.get("/api/v1/me/assignments", headers=b).json()[0]["stage"] == "Study"
    assert client.get("/api/v1/me/assignments?status=cancelled", headers=a).json()[0]["status"] == "cancelled"
    # the one who left may rejoin (waitlisted this time)
    assert client.post(f"/api/v1/topics/{t.id}/volunteer", headers=a).json()["status"] == "waitlisted"


def test_concurrent_style_duplicate_join_is_rejected(client, make_topic, db):
    t = make_topic()
    h = as_user("race@neuleap.ai")
    client.post(f"/api/v1/topics/{t.id}/volunteer", headers=h)
    assert client.post(f"/api/v1/topics/{t.id}/volunteer", headers=h).status_code == 409
    assert db.query(Volunteer).filter(Volunteer.topic_id == t.id).count() == 1


def test_full_journey_to_badges_and_certificate(client, admin, reviewer, employee, make_topic, db):
    t = make_topic()
    client.post(f"/api/v1/topics/{t.id}/volunteer", headers=employee)
    assert any(b["badge"]["key"] == "first-volunteer" for b in client.get("/api/v1/me/badges", headers=employee).json())
    study = client.get("/api/v1/me/assignments", headers=employee).json()[0]
    assert client.post(f"/api/v1/assignments/{study['id']}/complete", headers=employee).json()["status"] == "completed"
    poc = next(x for x in client.get("/api/v1/me/assignments", headers=employee).json() if x["stage"] == "POC")
    assert client.post(f"/api/v1/assignments/{poc['id']}/complete", headers=employee).status_code == 200
    pres = next(x for x in client.get("/api/v1/me/assignments", headers=employee).json() if x["stage"] == "Presentation")
    # can't finish the last stage without an approved artifact
    assert client.post(f"/api/v1/assignments/{pres['id']}/complete", headers=employee).status_code == 409
    r = submit(client, employee, file_part(), assignment_id=pres["id"])
    assert r.status_code == 202 and r.json()["status"] == "pending_review" and r.json()["stage"] == "Presentation"
    art_id = r.json()["id"]
    assert client.post(f"/api/v1/artifacts/{art_id}/approve", json={}, headers=employee).status_code == 403
    assert client.post(f"/api/v1/artifacts/{art_id}/approve", json={"comment": "nice"}, headers=reviewer).status_code == 200
    assert client.post(f"/api/v1/assignments/{pres['id']}/complete", headers=employee).status_code == 200
    certs = client.get("/api/v1/me/certificates", headers=employee).json()
    assert len(certs) == 1
    pdf = client.get(f"/api/v1/certificates/{certs[0]['id']}/download", headers=employee)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and b"%%EOF" in pdf.content
    assert client.get(f"/api/v1/certificates/{certs[0]['id']}/download", headers=as_user("other@neuleap.ai")).status_code == 404
    assert client.get(f"/api/v1/certificates/{certs[0]['id']}/download", headers=admin).status_code == 200
    keys = {b["badge"]["key"] for b in client.get("/api/v1/me/badges", headers=employee).json()}
    assert {"first-volunteer", "artifact-contributor", "presenter"} <= keys
    notes = client.get("/api/v1/notifications", headers=employee).json()
    assert notes["total"] >= 4
    assert client.get("/api/v1/notifications", headers=as_user("other@neuleap.ai")).json()["total"] == 0
    nid = notes["items"][0]["id"]
    assert client.post(f"/api/v1/notifications/{nid}/read", headers=as_user("other@neuleap.ai")).status_code == 404
    assert client.post(f"/api/v1/notifications/{nid}/read", headers=employee).status_code == 204
    assert client.post("/api/v1/notifications/read-all", headers=employee).status_code == 204
    assert client.get("/api/v1/notifications?unread=true", headers=employee).json()["total"] == 0


def test_cannot_complete_someone_elses_assignment(client, make_topic):
    t = make_topic()
    client.post(f"/api/v1/topics/{t.id}/volunteer", headers=as_user("a@neuleap.ai"))
    aid = client.get("/api/v1/me/assignments", headers=as_user("a@neuleap.ai")).json()[0]["id"]
    assert client.post(f"/api/v1/assignments/{aid}/complete", headers=as_user("b@neuleap.ai")).status_code == 404


def test_volunteer_list_is_admin_only(client, admin, employee, make_topic):
    t = make_topic()
    client.post(f"/api/v1/topics/{t.id}/volunteer", headers=employee)
    assert client.get(f"/api/v1/topics/{t.id}/volunteers", headers=employee).status_code == 403
    assert client.get(f"/api/v1/topics/{t.id}/volunteers", headers=admin).json()["total"] == 1
