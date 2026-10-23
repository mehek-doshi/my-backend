"""Celery tasks: thin wrappers that open a session and call the idempotent job bodies."""
from __future__ import annotations

import uuid

from app.db.session import new_session
from app.worker import jobs
from app.worker.celery_app import celery_app
from app.core.config import get_settings

RETRY = dict(autoretry_for=(jobs.JobFailed, ConnectionError, TimeoutError), retry_backoff=30, retry_backoff_max=900,
             retry_jitter=True, max_retries=4)


def _scheduled(name: str, fn, minutes: int):
    db = new_session()
    try:
        row, ran = jobs.run_job_once(db, name, f"{name}:{jobs.bucket(minutes)}", fn)
        return {"ran": ran, "status": row.status.value}
    finally:
        db.close()


@celery_app.task(name="techradar.run_discovery_session", bind=True, acks_late=True)
def run_discovery_session(self, session_id: str):
    """No auto-retry: a failed run is stored as 'failed' and an admin (or the next schedule) starts a new one."""
    from app.core.services import get_services
    from app.orchestrator.discovery import execute_discovery
    db = new_session()
    try:
        execute_discovery(db, uuid.UUID(session_id), get_services())
    finally:
        db.close()


@celery_app.task(name="techradar.scan_artifact", bind=True, **RETRY)
def scan_artifact(self, artifact_id: str):
    from app.services.artifacts import process_scan
    db = new_session()
    try:
        process_scan(db, uuid.UUID(artifact_id))
    finally:
        db.close()


@celery_app.task(name="techradar.scheduled_discovery", bind=True, **RETRY)
def scheduled_discovery(self):
    return _scheduled("scheduled_discovery", jobs.scheduled_discovery, get_settings().discovery_interval_minutes)


@celery_app.task(name="techradar.send_reminders", bind=True, **RETRY)
def send_reminders(self):
    return _scheduled("send_reminders", jobs.send_reminders, get_settings().reminder_interval_minutes)


@celery_app.task(name="techradar.sync_sharepoint", bind=True, **RETRY)
def sync_sharepoint(self):
    return _scheduled("sync_sharepoint", jobs.sync_sharepoint, get_settings().sharepoint_sync_interval_minutes)


@celery_app.task(name="techradar.sync_directory", bind=True, **RETRY)
def sync_directory(self):
    return _scheduled("sync_directory", jobs.sync_directory, get_settings().directory_sync_interval_minutes)


@celery_app.task(name="techradar.deliver_notifications", bind=True, **RETRY)
def deliver_notifications(self):
    return _scheduled("deliver_notifications", jobs.deliver_notifications, get_settings().notification_delivery_interval_minutes)


@celery_app.task(name="techradar.reap_stale", bind=True, **RETRY)
def reap_stale(self):
    return _scheduled("reap_stale", jobs.reap_stale, get_settings().reaper_interval_minutes)
