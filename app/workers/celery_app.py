
from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "ai_workflow_rescue",
    broker=(
 settings.REDIS_URL
    ),
    include=["app.workers.order_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_default_queue="workflow",
    task_routes={
        "app.workers.order_tasks.process_order": {
            "queue": "workflow",
        },
    },
)
