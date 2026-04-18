"""Celery tasks for the Google Ads Power Pack recommendation engine.

Scheduled via celery_app.py beat_schedule. Each task wraps a SessionLocal,
runs the orchestrator for a given cadence tag, and retries on failure.

All times in the schedule are UTC (Asia/Ho_Chi_Minh is UTC+7).
"""

import logging
import uuid

from app.database import SessionLocal
from app.services.google_recommendations import engine as rec_engine
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(cadence: str, source: str) -> dict:
    task_id = f"{source}:{uuid.uuid4().hex[:8]}"
    logger.info("Starting %s recommendation run (task_id=%s)", cadence, task_id)
    db = SessionLocal()
    try:
        stats = rec_engine.run_recommendations(
            db, cadence=cadence, source_task_id=task_id,
        )
        logger.info(
            "Finished %s recommendation run: inserted=%d updated=%d superseded=%d expired=%d",
            cadence, stats.get("inserted", 0), stats.get("updated", 0),
            stats.get("superseded", 0), stats.get("expired", 0),
        )
        return {"cadence": cadence, "task_id": task_id, **stats}
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.google_recommendation_tasks.daily_google_recommendations_task",
    bind=True, max_retries=3,
)
def daily_google_recommendations_task(self):
    """Runs daily detectors (spend/budget anomalies, impression drops,
    zero-conversion days, policy violations, tCPA change alarms)."""
    try:
        return _run("daily", source="beat:daily")
    except Exception as exc:
        logger.exception("daily_google_recommendations_task failed")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    name="app.tasks.google_recommendation_tasks.weekly_google_recommendations_task",
    bind=True, max_retries=3,
)
def weekly_google_recommendations_task(self):
    """Runs weekly detectors (creative/asset coverage, PMax learning, brand leak,
    RSA quality, search term hygiene)."""
    try:
        return _run("weekly", source="beat:weekly")
    except Exception as exc:
        logger.exception("weekly_google_recommendations_task failed")
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(
    name="app.tasks.google_recommendation_tasks.monthly_google_recommendations_task",
    bind=True, max_retries=3,
)
def monthly_google_recommendations_task(self):
    """Runs monthly detectors (budget mix reallocation, Ads-vs-PMS
    reconciliation, Customer Match freshness, PMax scale vs rooms)."""
    try:
        return _run("monthly", source="beat:monthly")
    except Exception as exc:
        logger.exception("monthly_google_recommendations_task failed")
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(
    name="app.tasks.google_recommendation_tasks.seasonality_lookahead_task",
    bind=True, max_retries=3,
)
def seasonality_lookahead_task(self):
    """Runs the seasonality cadence — events approaching their lead-time window
    and tCPA adjustments due during active peaks."""
    try:
        return _run("seasonality", source="beat:seasonality")
    except Exception as exc:
        logger.exception("seasonality_lookahead_task failed")
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(
    name="app.tasks.google_recommendation_tasks.expire_google_recommendations_task",
    bind=True, max_retries=2,
)
def expire_google_recommendations_task(self):
    """Hourly: flip pending rows past expires_at to status='expired'.

    Intentionally does NOT run detectors — this is only for expiry cleanup.
    """
    db = SessionLocal()
    try:
        count = rec_engine._expire_stale(db)
        db.commit()
        logger.info("Expired %d stale pending recommendations", count)
        return {"expired": count}
    except Exception as exc:
        logger.exception("expire_google_recommendations_task failed")
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()
