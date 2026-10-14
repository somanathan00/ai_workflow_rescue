
import logging
from uuid import UUID

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

        logger.exception(
            "Workflow failed: %s",
            decision.error_code,
            extra={"workflow_id": workflow_id},
        )

        with SessionLocal() as db:
            WorkflowService.record_failure(
                db=db,
                workflow_id=parsed_id,
                error_code=decision.error_code,
                error_message=str(exc),
                requires_review=decision.requires_review,
            )

        # Expected failures are persisted as workflow states.
        # Automatic retries are intentionally not enabled yet.
