from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "ads_platform",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Celery Beat schedule (times in UTC — Asia/Taipei is UTC+8)
celery_app.conf.beat_schedule = {
    # Daily at 23:00 UTC (07:00 Asia/Taipei next day): re-enable yesterday's paused ads,
    # sync all platforms, auto-classify combos, auto-assign angle+keypoints, eval rules.
    "daily-rule-cycle": {
        "task": "app.tasks.sync_tasks.daily_rule_cycle_task",
        "schedule": crontab(hour=23, minute=0),
    },
    # Daily at 00:00 UTC (08:00 Asia/Taipei): sync PMS reservations and run booking matching
    "sync-reservations-and-match": {
        "task": "app.tasks.sync_tasks.sync_reservations_and_match_task",
        "schedule": crontab(hour=0, minute=0),
    },
    # Weekly on Monday at 01:00 UTC (09:00 Asia/Taipei): refresh Meta creative preview URLs
    # (Meta CDN URLs expire after ~a few weeks; weekly refresh keeps thumbnails alive)
    "sync-material-urls-weekly": {
        "task": "app.tasks.sync_tasks.sync_material_urls_task",
        "schedule": crontab(hour=1, minute=0, day_of_week=1),
    },
}

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])
