"""
Celery application factory for the Sentinel worker.
"""
import os
from dotenv import load_dotenv

load_dotenv()

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

app = Celery(
    "sentinel",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["apps.worker.tasks"],
)

app.config_from_object("apps.worker.beat_schedule")

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "apps.worker.tasks.scan_region": {"queue": "scanning"},
        "apps.worker.tasks.classify_change": {"queue": "scanning"},
        "apps.worker.tasks.send_alert": {"queue": "alerts"},
        "apps.worker.tasks.scan_all_regions": {"queue": "default"},
        "apps.worker.tasks.dispatch_pending_alerts": {"queue": "default"},
    },
)

if __name__ == "__main__":
    app.start()
