from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import OutboxEventType
from app.infrastructure.messaging.outbox_publisher import (
    OutboxPublisher,
)
from app.models import (
    InventoryReservation,
    Order,
    Workflow,
    WorkflowEvent,
    WorkflowOperation,
)
from app.services.workflow_service import WorkflowNotFound


class ReconciliationNotAllowed(Exception):
    """The workflow is not in a state that can be reconciled."""


class ReconciliationConflict(Exception):
    """The provider state contradicts the original order."""


@dataclass(frozen=True)
class ReconciliationResult:
    workflow_id: UUID
    operation_status: str
    reservation_found: bool
    next_step: str | None
    workflow_status: str


class ReconciliationService:

    @staticmethod
    def find_matching_reservation(
        db: Session,
        order: Order,
    ) -> InventoryReservation | None:
        """Read-only check of what the provider actually holds."""
        reservation = db.scalar(
            select(InventoryReservation).where(
                InventoryReservation.order_id == order.id
            )
        )

        if reservation is None:
            return None

        if (
            reservation.product_id != order.product_id
            or reservation.quantity != order.quantity
            or reservation.status != "reserved"
        ):
            raise ValueError(
                "Reservation exists but does not match "
                "the original order"
            )

        return reservation

    @staticmethod
    def _event(
        db: Session,
        workflow: Workflow,
        event_type: str,
        details: dict | None = None,
    ) -> None:
        db.add(
            WorkflowEvent(
                workflow_id=workflow.id,
                step=workflow.current_step,
                event_type=event_type,
                details=details or {},
            )
        )

    @staticmethod
    def reconcile_reservation(
        db: Session,
        workflow_id: UUID,
    ) -> ReconciliationResult:
        """Verify an uncertain reservation and, if it matches the order,
        resume the workflow from invoice generation.

        Idempotent: repeating the call after a successful reconciliation
        returns the same outcome and creates no second resume.
        """
        conflict: str | None = None

        workflow = db.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .with_for_update()
        )

        if workflow is None:
            db.rollback()
            raise WorkflowNotFound(f"Workflow {workflow_id} not found")

        order = db.get(Order, workflow.order_id)
        operation = db.scalar(
            select(WorkflowOperation)
            .where(
                WorkflowOperation.operation_key
                == f"reserve:{workflow.order_id}"
            )
            .with_for_update()
        )

        if order is None or operation is None:
            db.rollback()
            raise ReconciliationNotAllowed(
                "Workflow has no reservation operation to reconcile"
            )

        # Already reconciled: report the current state. The resume
        # message was written with the original reconciliation, so the
        # outbox guarantees delivery; nothing more to enqueue.
        if (
            operation.status == "confirmed"
            and workflow.current_step != "reserve_inventory"
        ):
            result = ReconciliationResult(
                workflow_id=workflow.id,
                operation_status=operation.status,
                reservation_found=True,
                next_step=workflow.current_step,
                workflow_status=workflow.status,
            )
            db.rollback()
            return result

        if (
            workflow.status != "needs_review"
            or workflow.current_step != "reserve_inventory"
            or operation.status != "uncertain"
        ):
            db.rollback()
            raise ReconciliationNotAllowed(
                "Only a workflow waiting for review at "
                "reserve_inventory with an uncertain reservation "
                "can be reconciled"
            )

        ReconciliationService._event(
            db, workflow, "reconciliation_started",
            {"operation_key": operation.operation_key},
        )

        try:
            reservation = ReconciliationService.find_matching_reservation(
                db, order
            )
        except ValueError as exc:
            reservation = None
            conflict = str(exc)

        if conflict is not None:
            ReconciliationService._event(
                db, workflow, "reconciliation_conflict",
                {"message": conflict},
            )
            db.commit()
            raise ReconciliationConflict(conflict)

        if reservation is None:
            # Absence is not proof the operation never ran.
            ReconciliationService._event(
                db, workflow, "reconciliation_inconclusive",
                {"message": "No matching reservation was found"},
            )
            result = ReconciliationResult(
                workflow_id=workflow.id,
                operation_status=operation.status,
                reservation_found=False,
                next_step=workflow.current_step,
                workflow_status=workflow.status,
            )
            db.commit()
            return result

        previous_error = {
            "error_code": workflow.last_error_code,
            "message": workflow.last_error_message,
        }

        operation.status = "confirmed"
        operation.external_reference = str(reservation.id)
        operation.last_error_code = None
        operation.claim_token = None
        operation.claim_expires_at = None

        ReconciliationService._event(
            db, workflow, "reservation_confirmed",
            {
                "reservation_id": str(reservation.id),
                "operation_key": operation.operation_key,
            },
        )
        ReconciliationService._event(
            db, workflow, "step_completed",
            {"resolved_by": "reconciliation"},
        )

        workflow.current_step = "generate_invoice"
        workflow.status = "pending"
        # A resumed workflow starts a fresh processing cycle.
        workflow.attempts = 0
        workflow.next_retry_at = None
        workflow.last_error_code = None
        workflow.last_error_message = None
        workflow.version += 1
        order.status = "processing"

        ReconciliationService._event(
            db, workflow, "reconciliation_completed",
            {"cleared_error": previous_error},
        )
        ReconciliationService._event(
            db, workflow, "workflow_resumed",
            {"resumed_at": datetime.now(UTC).isoformat()},
        )

        OutboxPublisher.add(
            db,
            OutboxEventType.WORKFLOW_RESUME,
            workflow.id,
            {"workflow_id": str(workflow.id)},
        )

        result = ReconciliationResult(
            workflow_id=workflow.id,
            operation_status=operation.status,
            reservation_found=True,
            next_step=workflow.current_step,
            workflow_status=workflow.status,
        )
        db.commit()
        return result
