import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.db.enums import (ArtifactStatus, AssignmentStatus, InvitationStatus, JobStatus, NotificationChannel,
                          NotificationStatus, RunStatus)
from app.db.models import (AgentRun, Artifact, Assignment, Invitation, JobExecution, Notification, User)
from app.db.types import utcnow
from app.integrations.base import DirectoryUser, IntegrationError, NotConfigured
from app.worker import jobs
from tests.conftest import as_user, file_part, submit

EMP = "employee@neuleap.ai"


# ---- run_job_once --------------------------------------------------------------------------------
def test_job_runs_once_per_key(db):
    calls = []
    fn = lambda d: calls.append(1) or {"n": 1}
    row, ran = jobs.run_job_once(db, "x", "x:1", fn)
    assert ran and row.status == JobStatus.SUCCEEDED and row.result == {"n": 1}
    row2, ran2 = jobs.run_job_once(db, "x", "x:1", fn)
    assert not ran2 and len(calls) == 1 and row2.id == row.id
    assert jobs.run_job_once(db, "x", "x:2", fn)[1] and len(calls) == 2


def test_failed_job_is_recorded_and_retried_with_same_key(db):
    state = {"fail": True}

    def fn(d):
        if state["fail"]:
            raise RuntimeError("boom")
        return {"ok": True}

    with pytest.raises(jobs.JobFailed):
        jobs.run_job_once(db, "y", "y:1", fn)
    row = db.scalar(select(JobExecution).where(JobExecution.idempotency_key == "y:1"))
    assert row.status == JobStatus.FAILED and "boom" in row.error and row.attempts == 1
    state["fail"] = False
    row, ran = jobs.run_job_once(db, "y", "y:1", fn)
    assert ran and row.status == JobStatus.SUCCEEDED and row.attempts == 2 and row.error is None


def test_running_job_is_not_started_twice_but_stale_lease_is_reclaimed(db):
    db.add(JobExecution(name="z", idempotency_key="z:1", status=JobStatus.RUNNING, started_at=utcnow()))
    db.commit()
    called = []
    assert jobs.run_job_once(db, "z", "z:1", lambda d: called.append(1))[1] is False
    row = db.scalar(select(JobExecution).where(JobExecution.idempotency_key == "z:1"))
    row.started_at = utcnow() - timedelta(hours=2)
    db.commit()
    assert jobs.run_job_once(db, "z", "z:1", lambda d: called.append(1))[1] is True and called


def test_not_configured_is_skipped_not_failed(db):
    def fn(d):
        raise NotConfigured("nope")
    row, ran = jobs.run_job_once(db, "s", "s:1", fn)
    assert row.status == JobStatus.SKIPPED and row.error == "nope"


# ---- reminders -----------------------------------------------------------------------------------------
def test_reminders_expire_invitations_and_dedupe(client, admin, employee, make_topic, db):
    t = make_topic()
    inv = client.post(f"/api/v1/topics/{t.id}/invitations", json={"emails": [EMP]}, headers=admin).json()[0]
    row = db.get(Invitation, uuid.UUID(inv["id"]))
    row.created_at = utcnow() - timedelta(days=2)
    db.commit()
    s1 = jobs.send_reminders(db); db.commit()
    assert s1["invitation_reminders"] == 1
    s2 = jobs.send_reminders(db); db.commit()
    assert s2["invitation_reminders"] == 0  # reminded recently
    row = db.get(Invitation, uuid.UUID(inv["id"]))
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert jobs.send_reminders(db)["invitations_expired"] == 1
    db.commit()
    assert db.get(Invitation, uuid.UUID(inv["id"])).status == InvitationStatus.EXPIRED


def test_assignment_reminders_due_soon_and_overdue(client, employee, make_topic, db):
    t = make_topic()
    client.post(f"/api/v1/topics/{t.id}/volunteer", headers=employee)
    a = db.scalar(select(Assignment))
    a.due_at = utcnow() + timedelta(hours=3)
    db.commit()
    assert jobs.send_reminders(db)["due_soon"] == 1; db.commit()
    assert jobs.send_reminders(db)["due_soon"] == 0
    a = db.scalar(select(Assignment))
    a.due_at, a.last_reminded_at = utcnow() - timedelta(hours=1), utcnow() - timedelta(days=2)
    db.commit()
    assert jobs.send_reminders(db)["overdue"] == 1; db.commit()
    kinds = {n.kind for n in db.scalars(select(Notification).where(Notification.user_id == a.user_id))}
    assert {"assignment_due_soon", "assignment_overdue"} <= kinds


def test_reminders_do_not_touch_completed_assignments(client, employee, make_topic, db):
    t = make_topic()
    client.post(f"/api/v1/topics/{t.id}/volunteer", headers=employee)
    a = db.scalar(select(Assignment))
    a.due_at, a.status = utcnow() - timedelta(days=1), AssignmentStatus.COMPLETED
    db.commit()
    assert jobs.send_reminders(db)["overdue"] == 0


# ---- directory sync --------------------------------------------------------------------------------------
def test_directory_sync_updates_and_deactivates(db, integrations):
    integrations.directory.users = [
        DirectoryUser("oid-9", EMP, "Emma Employee", "Engineer", "Platform", True),
        DirectoryUser("oid-10", "admin@neuleap.ai", "Ada Admin", None, None, False),
        DirectoryUser("oid-11", "newbie@neuleap.ai", "New Person", None, None, True)]
    stats = jobs.sync_directory(db); db.commit()
    assert stats["updated"] == 2 and stats["deactivated"] == 1 and stats["created"] == 0
    u = db.scalar(select(User).where(User.email == EMP))
    assert u.display_name == "Emma Employee" and u.team == "Platform" and u.entra_object_id == "oid-9"
    assert db.scalar(select(User).where(User.email == "admin@neuleap.ai")).is_active is False
    assert db.scalar(select(User).where(User.email == "newbie@neuleap.ai")) is None


def test_directory_sync_can_create_users_when_enabled(db, integrations, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "directory_create_users", True)
    integrations.directory.users = [DirectoryUser("o1", "newbie@neuleap.ai", "New", enabled=True), DirectoryUser("o2", "x@other.com", "X")]
    assert jobs.sync_directory(db)["created"] == 1


def test_directory_sync_unconfigured_is_skipped(db):
    row, _ = jobs.run_job_once(db, "sync_directory", "sd:1", jobs.sync_directory)
    assert row.status == JobStatus.SKIPPED


# ---- SharePoint sync ------------------------------------------------------------------------------------------
def test_sharepoint_sync_uploads_only_approved(client, employee, reviewer, integrations, db):
    a = submit(client, employee, file_part()).json()
    b = submit(client, employee, file_part("two.md", b"# two"), title="Second").json()
    client.post(f"/api/v1/artifacts/{a['id']}/approve", json={}, headers=reviewer)
    stats = jobs.sync_sharepoint(db); db.commit()
    assert stats == {"uploaded": 1, "failed": 0} and len(integrations.sharepoint.files) == 1
    assert db.get(Artifact, uuid.UUID(a["id"])).sharepoint_item_id and db.get(Artifact, uuid.UUID(b["id"])).sharepoint_item_id is None
    assert jobs.sync_sharepoint(db) == {"uploaded": 0, "failed": 0}  # nothing left to do


def test_sharepoint_failure_is_stored_and_retried(client, employee, reviewer, integrations, db):
    a = submit(client, employee, file_part()).json()
    client.post(f"/api/v1/artifacts/{a['id']}/approve", json={}, headers=reviewer)
    integrations.sharepoint.fail = True
    assert jobs.sync_sharepoint(db)["failed"] == 1; db.commit()
    assert "IntegrationError" in db.get(Artifact, uuid.UUID(a["id"])).sync_error
    integrations.sharepoint.fail = False
    assert jobs.sync_sharepoint(db)["uploaded"] == 1; db.commit()
    assert db.get(Artifact, uuid.UUID(a["id"])).sync_error is None


def test_sharepoint_unconfigured_is_skipped(db):
    assert jobs.run_job_once(db, "sync_sharepoint", "sp:1", jobs.sync_sharepoint)[0].status == JobStatus.SKIPPED


# ---- notification delivery ----------------------------------------------------------------------------------------
def test_external_notifications_are_queued_and_delivered(client, admin, make_topic, integrations, monkeypatch, db):
    from app.core.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "mail_provider", "mock"); monkeypatch.setattr(s, "teams_provider", "mock")
    t = make_topic()
    client.post(f"/api/v1/topics/{t.id}/invitations", json={"emails": [EMP]}, headers=admin)
    # a user must exist to be invited
    client.get("/api/v1/auth/me", headers=as_user(EMP))
    rows = db.scalars(select(Notification).where(Notification.status == NotificationStatus.PENDING)).all()
    assert {n.channel for n in rows} == {NotificationChannel.EMAIL, NotificationChannel.TEAMS}
    stats = jobs.deliver_notifications(db); db.commit()
    assert stats["sent"] == 2 and len(integrations.mail.sent) == 1 and integrations.mail.sent[0][0] == EMP and len(integrations.teams.posts) == 1


def test_delivery_failure_retries_then_gives_up(db, integrations):
    u = db.scalar(select(User).where(User.email == EMP))
    db.add(Notification(user_id=u.id, kind="k", title="T", channel=NotificationChannel.EMAIL, status=NotificationStatus.PENDING))
    db.commit()
    integrations.mail.fail = True
    for i in range(jobs.MAX_DELIVERY_ATTEMPTS):
        assert jobs.deliver_notifications(db)["failed"] == 1; db.commit()
    n = db.scalar(select(Notification).where(Notification.channel == NotificationChannel.EMAIL))
    assert n.status == NotificationStatus.FAILED
    assert jobs.deliver_notifications(db) == {"sent": 0, "failed": 0, "skipped": 0}


def test_unconfigured_channel_is_skipped(db):
    u = db.scalar(select(User).where(User.email == EMP))
    db.add(Notification(user_id=u.id, kind="k", title="T", channel=NotificationChannel.EMAIL, status=NotificationStatus.PENDING))
    db.commit()
    assert jobs.deliver_notifications(db)["skipped"] == 1


def test_notification_dedupe_key_prevents_duplicates(db):
    from app.services.notifications import notify
    u = db.scalar(select(User).where(User.email == EMP))
    assert notify(db, u.id, "k", "T", dedupe_key="same") is True
    assert notify(db, u.id, "k", "T", dedupe_key="same") is False
    db.commit()
    assert db.query(Notification).filter(Notification.dedupe_key == "same").count() == 1


# ---- scheduled discovery / reaper ------------------------------------------------------------------------------
def test_scheduled_discovery_is_idempotent_per_interval(client, admin, services, db):
    client.post("/api/v1/sources", json={"name": "Example", "url": "https://blog.example.com/feed.xml"}, headers=admin)
    r1, ran1 = jobs.run_job_once(db, "scheduled_discovery", "sd:1", jobs.scheduled_discovery)
    assert ran1 and r1.result["created"] is True
    r2 = jobs.scheduled_discovery(db)  # same time bucket, called outside run_job_once
    assert r2["created"] is False
    assert db.query(AgentRun).filter(AgentRun.workflow == "discovery").count() == 1


def test_reaper_fails_dead_runs_and_requeues_stuck_scans(client, employee, db):
    dead = AgentRun(workflow="discovery", status=RunStatus.RUNNING, started_at=utcnow() - timedelta(hours=3), heartbeat_at=utcnow() - timedelta(hours=3))
    db.add(dead)
    a = submit(client, employee, file_part()).json()
    art = db.get(Artifact, uuid.UUID(a["id"]))
    art.status, art.updated_at = ArtifactStatus.SCANNING, utcnow() - timedelta(hours=3)
    db.commit()
    stats = jobs.reap_stale(db)
    assert stats["runs_failed"] == 1 and stats["scans_requeued"] == 1
    db.expire_all()
    assert db.get(AgentRun, dead.id).status == RunStatus.FAILED
    assert db.get(Artifact, art.id).status == ArtifactStatus.PENDING_REVIEW  # re-scanned (eager mode)


# ---- Celery wiring ---------------------------------------------------------------------------------------------------
def test_beat_schedule_comes_from_settings_with_spec_defaults():
    from app.core.config import Settings
    from app.worker.celery_app import build_beat_schedule
    sch = build_beat_schedule(Settings(_env_file=None, environment="test", auth_mode="entra"))
    assert sch["discovery"]["schedule"] == 6 * 3600 and sch["reminders"]["schedule"] == 3600
    assert sch["sharepoint-sync"]["schedule"] == 300 and sch["directory-sync"]["schedule"] == 3600
    custom = build_beat_schedule(Settings(_env_file=None, environment="test", auth_mode="entra", discovery_interval_minutes=15))
    assert custom["discovery"]["schedule"] == 900


def test_celery_is_configured_for_safe_redelivery():
    from app.worker.celery_app import celery_app
    c = celery_app.conf
    assert c.task_acks_late and c.task_reject_on_worker_lost and c.worker_prefetch_multiplier == 1
    registered = {"techradar.scan_artifact", "techradar.run_discovery_session", "techradar.scheduled_discovery",
                  "techradar.send_reminders", "techradar.sync_sharepoint", "techradar.sync_directory",
                  "techradar.deliver_notifications", "techradar.reap_stale"}
    import app.worker.tasks  # noqa: F401
    assert registered <= set(celery_app.tasks)
    assert {v["task"] for v in c.beat_schedule.values()} <= registered


def test_celery_task_runs_through_task_wrapper_in_eager_mode(db, client, employee):
    from app.worker.tasks import scan_artifact
    a = submit(client, employee, file_part()).json()
    res = scan_artifact.apply(args=[a["id"]])
    assert res.successful()


def test_admin_integration_status_is_honest(client, admin, integrations):
    st = client.get("/api/v1/admin/integrations", headers=admin).json()
    assert st["sharepoint"]["mock"] is True and all(v["verified_against_live_system"] is False for v in st.values())
    assert client.get("/api/v1/admin/integrations", headers=as_user(EMP)).status_code == 403
