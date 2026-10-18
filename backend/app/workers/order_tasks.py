import logging
from uuid import UUID

from app.core.config import settings
from app.domain.policies.retry_policy import RetryPolicy
from app.infrastructure.database.session import SessionLocal
from app.services.workflow_service import WorkflowService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.order_tasks.process_order",
    bind=True,
)
def process_order(self, workflow_id: str) -> None:
    parsed_id = UUID(workflow_id)

    try:
        with SessionLocal() as db:
            WorkflowService.process(
                db=db,
                workflow_id=parsed_id,
            )

    except Exception as exc:
        decision = RetryPolicy.classify(exc)

        if decision.error_code == "UNEXPECTED_ERROR":
            logger.exception(
                "Workflow failed: %s",
                decision.error_code,
                extra={"workflow_id": workflow_id},
            )
        else:
            # Classified, expected failure: no stack trace needed.
            logger.warning(
                "Workflow failed: %s",
                decision.error_code,
                extra={
                    "workflow_id": workflow_id,
                    "error_code": decision.error_code,
                    "error": str(exc)[:300],
                },
            )

        with SessionLocal() as db:
            delay = WorkflowService.record_failure(
                db=db,
                workflow_id=parsed_id,
                error_code=decision.error_code,
                error_message=str(exc),
                requires_review=decision.requires_review,
                retryable=decision.retryable,
                jitter=settings.ENVIRONMENT == "production",
            )

        if delay is not None:
            # The retry is already durable in PostgreSQL
            # (status=retry_scheduled, next_retry_at). If publishing fails,
            # requeue_due_retries will re-enqueue it.
            logger.info(
                "workflow_retry_scheduled",
                extra={
                    "workflow_id": workflow_id,
                    "error_code": decision.error_code,
                    "retry_delay_seconds": delay,
                },
            )
            try:
                self.apply_async(
                    args=[workflow_id],
                    countdown=delay,
                    queue="workflow",
                )
            except Exception:
                logger.warning(
                    "Could not publish retry; the due-retry sweep "
                    "will re-enqueue it",
                    exc_info=True,
                    extra={"workflow_id": workflow_id},
                )


@celery_app.task(name="app.workers.order_tasks.requeue_due_retries")
def requeue_due_retries() -> int:
    """Re-enqueue overdue retry_scheduled workflows. Duplicates are safe:
    process_order only claims a retry that is due and still scheduled."""
    with SessionLocal() as db:
        workflow_ids = WorkflowService.due_retry_ids(db)

    for workflow_id in workflow_ids:
        process_order.apply_async(
            args=[str(workflow_id)],
            queue="workflow",
        )

    return len(workflow_ids)
