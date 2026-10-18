import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.domain.enums import OutboxEventType
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.messaging.outbox_publisher import OutboxPublisher
from app.models import OutboxMessage, WorkflowRecoveryAction
from app.services.recovery_service import RecoveryService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.recovery_tasks.execute_recovery")
def execute_recovery(recovery_action_id: str) -> None:
    with SessionLocal() as db:
        RecoveryService.execute(db, UUID(recovery_action_id))


@celery_app.task(name="app.workers.recovery_tasks.reclaim_stale_recoveries")
def reclaim_stale_recoveries() -> int:
    """Re-deliver recoveries whose worker died mid-execution (lease
    expired). Execution is idempotent, so a duplicate is harmless."""
    reclaimed = 0

    with SessionLocal.begin() as db:
        stale_ids = db.scalars(
            select(WorkflowRecoveryAction.id).where(
                WorkflowRecoveryAction.status == "executing",
                WorkflowRecoveryAction.claim_expires_at
                < datetime.now(UTC),
            )
        ).all()

        for action_id in stale_ids:
            already_queued = db.scalar(
                select(OutboxMessage.id).where(
                    OutboxMessage.aggregate_id == action_id,
                    OutboxMessage.event_type
                    == OutboxEventType.RECOVERY_EXECUTE.value,
                    OutboxMessage.status == "pending",
                )
            )

            if already_queued is None:
                OutboxPublisher.add(
                    db,
                    OutboxEventType.RECOVERY_EXECUTE,
                    action_id,
                    {"recovery_action_id": str(action_id)},
                )
                reclaimed += 1

    return reclaimed
