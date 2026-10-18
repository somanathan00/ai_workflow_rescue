
from celery import Celery
from celery.signals import setup_logging

from app.core.config import settings
from app.core.logging import configure_logging


@setup_logging.connect
def _configure_logging(**_kwargs) -> None:
    configure_logging()


celery_app = Celery(
    "ai_workflow_rescue",
    broker=(
 settings.REDIS_URL
    ),
    include=[
        "app.workers.order_tasks",
        "app.workers.recovery_tasks",
        "app.workers.investigation_tasks",
    ],
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
    broker_connection_timeout=2,
    broker_transport_options={
        "socket_connect_timeout": 2,
        "socket_timeout": 5,
    },
    beat_schedule={
        "reclaim-stale-recoveries": {
            "task": "app.workers.recovery_tasks.reclaim_stale_recoveries",
            "schedule": 60.0,
        },
        "requeue-due-retries": {
            "task": "app.workers.order_tasks.requeue_due_retries",
            "schedule": 30.0,
        },
    },
    task_routes={
        "app.workers.order_tasks.process_order": {
            "queue": "workflow",
        },
    },
)
