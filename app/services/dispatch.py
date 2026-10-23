"""Hand work to Celery. In eager mode (tests / local without Redis) the work runs inline instead."""
from __future__ import annotations

import logging
import uuid

from app.core.config import get_settings


def enqueue_discovery(session_id: uuid.UUID) -> str | None:
    if get_settings().celery_task_always_eager:
        from app.db.session import new_session
        from app.core.services import get_services
        from app.orchestrator.discovery import execute_discovery
        db = new_session()
        try:
            execute_discovery(db, session_id, get_services())
        except Exception:  # the failure is already stored on the run; the caller just sees status 'failed'
            logging.getLogger("techradar.dispatch").exception("Inline discovery failed")
        finally:
            db.close()
        return None
    from app.worker.tasks import run_discovery_session
    return run_discovery_session.delay(str(session_id)).id


def enqueue_artifact_scan(artifact_id: uuid.UUID) -> str | None:
    if get_settings().celery_task_always_eager:
        from app.db.session import new_session
        from app.services.artifacts import process_scan
        db = new_session()
        try:
            process_scan(db, artifact_id)
        except Exception:
            logging.getLogger("techradar.dispatch").exception("Inline artifact scan failed")
        finally:
            db.close()
        return None
    from app.worker.tasks import scan_artifact
    return scan_artifact.delay(str(artifact_id)).id
