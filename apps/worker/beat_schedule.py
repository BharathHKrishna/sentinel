"""
Celery Beat schedule configuration.

This module is loaded by celery_app.config_from_object().
"""
from celery.schedules import crontab

# Celery Beat schedule
beat_schedule = {
    # Scan all monitored regions every hour
    "scan-all-regions-hourly": {
        "task": "apps.worker.tasks.scan_all_regions",
        "schedule": crontab(minute=0),  # top of every hour
        "options": {"queue": "default"},
    },
    # Dispatch any pending alert notifications every 5 minutes
    "dispatch-pending-alerts-every-5m": {
        "task": "apps.worker.tasks.dispatch_pending_alerts",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "default"},
    },
}

# These are picked up by app.config_from_object()
beat_scheduler = "celery.beat:PersistentScheduler"
