"""Celery application. Start with (Windows needs --pool=solo):

    celery -A app.worker.celery_app worker --loglevel=INFO --pool=solo
    celery -A app.worker.celery_app beat   --loglevel=INFO          # the separate scheduler process
"""
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


def build_beat_schedule(s) -> dict:
    return {
        "discovery": {"task": "techradar.scheduled_discovery", "schedule": s.discovery_interval_minutes * 60.0},
        "reminders": {"task": "techradar.send_reminders", "schedule": s.reminder_interval_minutes * 60.0},
        "sharepoint-sync": {"task": "techradar.sync_sharepoint", "schedule": s.sharepoint_sync_interval_minutes * 60.0},
        "directory-sync": {"task": "techradar.sync_directory", "schedule": s.directory_sync_interval_minutes * 60.0},
        "notification-delivery": {"task": "techradar.deliver_notifications", "schedule": s.notification_delivery_interval_minutes * 60.0},
        "reaper": {"task": "techradar.reap_stale", "schedule": s.reaper_interval_minutes * 60.0},
    }


def make_celery() -> Celery:
    s = get_settings()
    app = Celery("techradar", broker=s.redis_url, include=["app.worker.tasks"])
    app.conf.update(
        task_acks_late=True,                 # a task is acknowledged after it finished, so a crashed worker's task is redelivered
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_ignore_result=True,             # results live in agent_runs / job_executions, not in Redis
        task_time_limit=60 * 60, task_soft_time_limit=55 * 60,
        task_always_eager=s.celery_task_always_eager, task_eager_propagates=False,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"visibility_timeout": 2 * 60 * 60},  # longer than the longest task, or Redis redelivers it while running
        timezone="UTC", enable_utc=True,
        beat_schedule=build_beat_schedule(s),
    )
    return app


celery_app = make_celery()
