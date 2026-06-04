"""
Celery application factory for the Sentinel worker.

Redis is optional — if REDIS_URL is not set, Celery is configured with
a dummy in-memory broker so the API starts cleanly. Tasks will fall back
to synchronous execution via the admin route's _run_scan_sync().
"""
import os
from dotenv import load_dotenv

load_dotenv()

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "")

# Use memory:// broker if Redis is not configured so the API starts without crashing.
# Task dispatch will fail gracefully and fall back to synchronous execution.
_broker = REDIS_URL if REDIS_URL else "memory://"
_backend = REDIS_URL if REDIS_URL else "cache+memory://"

app = Celery(
    "sentinel",
    broker=_broker,
    backend=_backend,
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
    broker_connection_retry_on_startup=False,
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
