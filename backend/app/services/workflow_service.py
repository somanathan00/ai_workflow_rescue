
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.exceptions import (
    TransientWorkflowError,
    UncertainOutcomeError,
)
from app.domain.policies.retry_policy import RetryPolicy
from app.models import (
    Order,
    Workflow,
    WorkflowEvent,
    WorkflowOperation,
)
from app.services.failure_simulator import FailureSimulator
from app.services.invoice_service import InvoiceService
from app.services.simulated_inventory_provider import (
    SimulatedInventoryProvider,
)


class WorkflowNotFound(Exception):
    pass


RETRY_CLOCK_SLACK = timedelta(seconds=1)
TERMINAL_STATUSES = {"completed", "failed", "needs_review", "compensated"}
OPERATION_LEASE = timedelta(seconds=60)


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
    def _claim(db: Session, workflow_id: UUID) -> bool:
        """Claim one execution in its own committed transaction.

        Returns False when there is nothing to do (terminal, or a retry
        that is not due yet). Because the claim commits before any step
        runs, a failing step cannot roll back the attempt counter.
        """
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

            if workflow.status in TERMINAL_STATUSES:
                return False

            if workflow.status == "retry_scheduled":
                now = datetime.now(UTC)

                if (
                    workflow.next_retry_at is not None
                    and workflow.next_retry_at - now > RETRY_CLOCK_SLACK
                ):
                    # Early or duplicate delivery; the due-retry sweep
                    # (or the scheduled task) will pick it up later.
                    return False

                workflow.status = "processing"
                workflow.next_retry_at = None
                workflow.attempts += 1
                workflow.version += 1

                WorkflowService._event(
                    db,
                    workflow,
                    "retry_started",
                    workflow.current_step,
                    {"attempt": workflow.attempts},
                )

            elif workflow.status == "pending":
                workflow.status = "processing"
                order.status = "processing"
                workflow.attempts += 1
                workflow.version += 1

                WorkflowService._event(
                    db,
                    workflow,
                    "workflow_started",
                    workflow.current_step,
                    {"attempt": workflow.attempts},
                )

            # status == "processing": redelivery after a worker crash;
            # continue from the last committed step without a new attempt.
            return True

    @staticmethod
    def process(
        db: Session,
        workflow_id: UUID,
    ) -> None:
        if not WorkflowService._claim(db, workflow_id):
            return

        while True:
            run_reservation = False

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

                if workflow.status != "processing":
                    return

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
                    # The provider call must not run inside this
                    # transaction; see _reserve_inventory.
                    run_reservation = True

                elif step == "generate_invoice":
                    FailureSimulator.before_invoice_generation(
                        order.product_id
                    )

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

                if not run_reservation:
                    workflow.version += 1

            if run_reservation and not WorkflowService._reserve_inventory(
                db, workflow_id
            ):
                return

    @staticmethod
    def _reserve_inventory(db: Session, workflow_id: UUID) -> bool:
        """Reserve inventory across three short transactions.

        1. Prepare: lock the workflow, create or load the operation and
           take its lease. Nothing external has happened yet.
        2. Call the provider with no transaction or row lock held.
        3. Settle: confirm the operation and advance, or record that the
           outcome is uncertain. Only the lease holder may settle.

        Returns True when the workflow advanced and the caller should
        keep processing, False when it should stop.
        """
        token = uuid.uuid4().hex

        # 1. Prepare
        with db.begin():
            workflow = db.scalar(
                select(Workflow)
                .where(Workflow.id == workflow_id)
                .with_for_update()
            )

            if (
                workflow is None
                or workflow.status != "processing"
                or workflow.current_step != "reserve_inventory"
            ):
                return False

            order = db.get(Order, workflow.order_id)

            if order is None:
                raise WorkflowNotFound(
                    "Workflow references a missing order"
                )

            FailureSimulator.before_inventory_reservation(
                order.product_id,
                workflow.attempts,
            )

            key = f"reserve:{order.id}"
            operation = db.scalar(
                select(WorkflowOperation)
                .where(WorkflowOperation.operation_key == key)
                .with_for_update()
            )

            if operation is None:
                operation = WorkflowOperation(
                    workflow_id=workflow.id,
                    operation_key=key,
                    step="reserve_inventory",
                    status="pending",
                    attempts=0,
                )
                db.add(operation)
                db.flush()

            now = datetime.now(UTC)

            if operation.status == "uncertain":
                # Never call the provider again without reconciliation.
                raise UncertainOutcomeError(
                    "Reservation outcome is still uncertain"
                )

            if operation.status == "confirmed":
                # Provider call already settled (crash before advancing).
                WorkflowService._advance_after_reservation(
                    db, workflow, operation
                )
                return True

            if (
                operation.claim_token is not None
                and operation.claim_expires_at is not None
                and operation.claim_expires_at > now
            ):
                # Another worker holds the lease and will settle it.
                return False

            operation.claim_token = token
            operation.claim_expires_at = now + OPERATION_LEASE
            operation.status = "pending"
            operation.attempts += 1
            operation_attempt = operation.attempts

            WorkflowService._event(
                db,
                workflow,
                "reservation_requested",
                "reserve_inventory",
                {
                    "operation_key": key,
                    "operation_attempt": operation_attempt,
                },
            )

            order_id = order.id
            product_id = order.product_id
            quantity = order.quantity

        # 2. Provider call (no transaction held)
        try:
            reservation_id = SimulatedInventoryProvider.reserve(
                order_id=order_id,
                product_id=product_id,
                quantity=quantity,
                simulate_lost_response=(
                    FailureSimulator.lose_inventory_response(
                        product_id, operation_attempt
                    )
                ),
            )

        except UncertainOutcomeError as exc:
            # 3a. Settle as uncertain; the worker must not retry.
            with db.begin():
                workflow, operation = WorkflowService._lock_for_settle(
                    db, workflow_id, key, token
                )

                if operation is None:
                    return False

                operation.status = "uncertain"
                operation.last_error_code = "UNCERTAIN_OUTCOME"
                operation.claim_token = None
                operation.claim_expires_at = None

                workflow.status = "needs_review"
                workflow.last_error_code = "UNCERTAIN_OUTCOME"
                workflow.last_error_message = str(exc)[:1000]
                workflow.next_retry_at = None
                workflow.version += 1

                order = db.get(Order, workflow.order_id)

                if order is not None:
                    order.status = "failed"

                WorkflowService._event(
                    db,
                    workflow,
                    "reservation_outcome_uncertain",
                    "reserve_inventory",
                    {
                        "operation_key": key,
                        "message": str(exc)[:1000],
                    },
                )

            return False

        except Exception as exc:
            # Provider definitively did not complete: release the lease
            # and let the normal failure handling classify the error.
            with db.begin():
                workflow, operation = WorkflowService._lock_for_settle(
                    db, workflow_id, key, token
                )

                if operation is not None:
                    operation.claim_token = None
                    operation.claim_expires_at = None
                    operation.last_error_code = getattr(
                        exc, "error_code", "UNEXPECTED_ERROR"
                    )
                    operation.status = (
                        "pending"
                        if isinstance(exc, TransientWorkflowError)
                        else "failed"
                    )

            raise

        # 3b. Settle as confirmed and advance.
        with db.begin():
            workflow, operation = WorkflowService._lock_for_settle(
                db, workflow_id, key, token
            )

            if operation is None:
                return False

            operation.status = "confirmed"
            operation.external_reference = reservation_id
            operation.last_error_code = None
            operation.claim_token = None
            operation.claim_expires_at = None

            if (
                workflow.status == "processing"
                and workflow.current_step == "reserve_inventory"
            ):
                WorkflowService._advance_after_reservation(
                    db, workflow, operation
                )

        return True

    @staticmethod
    def _lock_for_settle(
        db: Session,
        workflow_id: UUID,
        key: str,
        token: str,
    ) -> tuple[Workflow, WorkflowOperation | None]:
        """Lock the workflow and operation; return no operation unless
        the caller still holds the lease."""
        workflow = db.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .with_for_update()
        )
        operation = db.scalar(
            select(WorkflowOperation)
            .where(WorkflowOperation.operation_key == key)
            .with_for_update()
        )

        if (
            workflow is None
            or operation is None
            or operation.claim_token != token
        ):
            return workflow, None

        return workflow, operation

    @staticmethod
    def _advance_after_reservation(
        db: Session,
        workflow: Workflow,
        operation: WorkflowOperation,
    ) -> None:
        WorkflowService._event(
            db,
            workflow,
            "step_completed",
            "reserve_inventory",
            {
                "operation_key": operation.operation_key,
                "reservation_id": operation.external_reference,
            },
        )
        workflow.current_step = "generate_invoice"
        workflow.version += 1

    @staticmethod
    def record_failure(
        db: Session,
        workflow_id: UUID,
        error_code: str,
        error_message: str,
        requires_review: bool = False,
        retryable: bool = False,
        jitter: bool = False,
    ) -> float | None:
        """Persist a failed execution.

        Returns the delay in seconds when a retry was scheduled, else None.
        """
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

            # Only an execution that is still in flight may fail it. This
            # keeps a stale or duplicate task from clobbering newer state.
            if workflow.status != "processing":
                return None

            workflow.last_error_code = error_code
            workflow.last_error_message = error_message[:1000]
            workflow.version += 1

            details = {
                "error_code": error_code,
                "message": error_message[:1000],
                "attempt": workflow.attempts,
            }

            WorkflowService._event(
                db,
                workflow,
                "step_failed",
                workflow.current_step,
                details,
            )

            delay = RetryPolicy.retry_delay(
                workflow.attempts, retryable, jitter
            )

            if delay is not None:
                workflow.status = "retry_scheduled"
                workflow.next_retry_at = (
                    datetime.now(UTC)
                    + timedelta(seconds=delay)
                )

                WorkflowService._event(
                    db,
                    workflow,
                    "retry_scheduled",
                    workflow.current_step,
                    {
                        "attempt": workflow.attempts + 1,
                        "delay_seconds": round(delay, 2),
                        "next_retry_at": (
                            workflow.next_retry_at.isoformat()
                        ),
                    },
                )

                return delay

            workflow.status = (
                "needs_review" if requires_review else "failed"
            )
            workflow.next_retry_at = None

            order = db.get(Order, workflow.order_id)

            if order is not None:
                order.status = "failed"

            WorkflowService._event(
                db,
                workflow,
                "workflow_failed",
                workflow.current_step,
                {
                    **details,
                    "requires_review": requires_review,
                    "retries_exhausted": (
                        retryable
                        and workflow.attempts
                        >= RetryPolicy.MAX_ATTEMPTS
                    ),
                },
            )

            return None

    @staticmethod
    def due_retry_ids(
        db: Session,
        grace: timedelta = timedelta(seconds=5),
        limit: int = 100,
    ) -> list[UUID]:
        """Workflows whose scheduled retry is overdue (for the sweep)."""
        cutoff = datetime.now(UTC) - grace

        return list(
            db.scalars(
                select(Workflow.id)
                .where(
                    Workflow.status == "retry_scheduled",
                    Workflow.next_retry_at <= cutoff,
                )
                .order_by(Workflow.next_retry_at)
                .limit(limit)
            )
        )
