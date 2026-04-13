"""
ROADAI Celery Application
=========================
Async background job queue using Redis as broker and backend.
Handles heavy data aggregation, report generation, and scheduled tasks.
"""
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/1")

celery_app = Celery(
    "roadai_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["backend.tasks.report_tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
)

if __name__ == "__main__":
    celery_app.start()
