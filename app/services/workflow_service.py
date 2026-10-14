
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Order,
    Workflow,
    WorkflowEvent,
)
from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService
from app.services.failure_simulator import FailureSimulator

class WorkflowNotFound(Exception):
    pass


class WorkflowService:

    @staticmethod
    def _event(
        db: Session,
        workflow: Workflow,
        event_type: str,
        step: str | None,
        details: dict | None = None,
    ) -> None:
        db.add(
            WorkflowEvent(
                workflow_id=workflow.id,
                event_type=event_type,
                step=step,
                details=details or {},
            )
        )

    @staticmethod
    def process(
        db: Session,
        workflow_id: UUID,
    ) -> None:
        while True:
            # Each iteration has its own short transaction.
            # Never share this Session between worker processes.
            with db.begin():
                workflow = db.scalar(
                    select(Workflow)
                    .where(Workflow.id == workflow_id)
                    .with_for_update()
                )

                if workflow is None:
                    raise WorkflowNotFound(
                        f"Workflow {workflow_id} not found"
                    )

                order = db.get(Order, workflow.order_id)

                if order is None:
                    raise WorkflowNotFound(
                        "Workflow references a missing order"
                    )

                if workflow.status in {
                    "completed",
                    "failed",
                    "needs_review",
                }:
                    return

                if workflow.status == "pending":
                    workflow.status = "processing"
                    order.status = "processing"

                    WorkflowService._event(
                        db,
                        workflow,
                        "workflow_started",
                        workflow.current_step,
                    )

                step = workflow.current_step

                if step == "validate_order":
                    if order.quantity <= 0:
                        raise ValueError(
                            "Order quantity must be positive"
                        )

                    if not order.product_id.strip():
                        raise ValueError(
                            "Product ID is required"
                        )

                    WorkflowService._event(
                        db,
                        workflow,
                        "step_completed",
                        step,
                    )

                    workflow.current_step = "reserve_inventory"

                elif step == "reserve_inventory":
                    FailureSimulator.before_inventory_reservation(
                        order.product_id
                    )

                    InventoryService.reserve(db, order)

                    WorkflowService._event(
                        db,
                        workflow,
                        "step_completed",
                        step,
                    )

                    workflow.current_step = "generate_invoice"

                elif step == "generate_invoice":
                    InvoiceService.generate(db, order)

                    WorkflowService._event(
                        db,
                        workflow,
                        "step_completed",
                        step,
                    )

                    workflow.current_step = None
                    workflow.status = "completed"
                    order.status = "completed"

                    WorkflowService._event(
                        db,
                        workflow,
                        "workflow_completed",
                        None,
                    )

                else:
                    raise ValueError(
                        f"Unknown workflow step: {step}"
                    )

                workflow.version += 1
                
    
    @staticmethod
    def record_failure(
        db: Session,
        workflow_id: UUID,
        error_code: str,
        error_message: str,
        requires_review: bool = False,
    ) -> None:
        with db.begin():
            workflow = db.scalar(
                select(Workflow)
                .where(Workflow.id == workflow_id)
                .with_for_update()
            )

            if workflow is None:
                raise WorkflowNotFound(
                    f"Workflow {workflow_id} not found"
                )

            if workflow.status == "completed":
                return

            workflow.status = (
                "needs_review"
                if requires_review
                else "failed"
            )

            workflow.attempts += 1
            workflow.last_error_code = error_code
            workflow.last_error_message = (
                error_message[:1000]
            )
            workflow.version += 1

            order = db.get(
                Order,
                workflow.order_id,
            )

            if order is not None:
                order.status = "failed"

            WorkflowService._event(
                db,
                workflow,
                "workflow_failed",
                workflow.current_step,
                {
                    "error_code": error_code,
                    "message": error_message[:1000],
                    "requires_review": requires_review,
                },
            )

