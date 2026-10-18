import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums import (
    ACTIVE_RECOVERY_STATUSES,
    OutboxEventType,
    RecoveryActionType,
    UserRole,
)
from app.domain.enums import (
    RecoveryActionStatus as S,
)
from app.domain.policies.recovery_policy import RecoveryPolicy
from app.infrastructure.messaging.outbox_publisher import OutboxPublisher
from app.models import (
    InventoryReservation,
    Investigation,
    Order,
    User,
    Workflow,
    WorkflowEvent,
    WorkflowOperation,
    WorkflowRecoveryAction,
)
from app.services.reconciliation_service import (
    ReconciliationConflict,
    ReconciliationNotAllowed,
    ReconciliationService,
)
from app.services.simulated_inventory_provider import (
    SimulatedInventoryProvider,
)

EXECUTION_LEASE = timedelta(minutes=5)


class RecoveryExecutionError(Exception):
    """An approved recovery could not be carried out."""


def _now() -> datetime:
    return datetime.now(UTC)


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN.value


def _fail(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


class RecoveryService:
    """Recovery state machine. Every transition runs under row locks and
    is re-validated against live workflow state."""

    # ------------------------------------------------------------ helpers
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
    def _lock_workflow(
        db: Session,
        workflow_id: UUID,
        user: User,
        owner_only: bool,
    ) -> Workflow:
        workflow = db.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .with_for_update()
        )
        order = (
            db.get(Order, workflow.order_id) if workflow else None
        )

        allowed = order is not None and (
            order.user_id == user.id
            or (_is_admin(user) and not owner_only)
        )

        if not allowed:
            db.rollback()
            # Same answer for "missing" and "not yours".
            raise _fail(404, "Workflow not found")

        return workflow

    @staticmethod
    def _lock_action(
        db: Session,
        workflow_id: UUID,
        action_id: UUID,
    ) -> WorkflowRecoveryAction:
        action = db.scalar(
            select(WorkflowRecoveryAction)
            .where(
                WorkflowRecoveryAction.id == action_id,
                WorkflowRecoveryAction.workflow_id == workflow_id,
            )
            .with_for_update()
        )

        if action is None:
            db.rollback()
            raise _fail(404, "Recovery action not found")

        return action

    @staticmethod
    def _transition(
        action: WorkflowRecoveryAction,
        new: S,
    ) -> None:
        if not RecoveryPolicy.can_transition(S(action.status), new):
            raise _fail(
                409,
                f"Cannot move recovery from {action.status} to {new}",
            )
        action.status = new.value

    @staticmethod
    def _reservation_status(db: Session, order_id: UUID) -> str | None:
        return db.scalar(
            select(InventoryReservation.status).where(
                InventoryReservation.order_id == order_id
            )
        )

    @staticmethod
    def _validate_policy(
        db: Session,
        workflow: Workflow,
        action_type: str,
    ) -> None:
        try:
            RecoveryPolicy.validate(
                workflow.status,
                workflow.last_error_code,
                RecoveryActionType(action_type),
                workflow.current_step,
                RecoveryService._reservation_status(db, workflow.order_id),
            )
        except ValueError as exc:
            db.rollback()
            raise _fail(409, str(exc)) from exc

    # ------------------------------------------------------------- reads
    @staticmethod
    def list_actions(
        db: Session,
        workflow_id: UUID,
        user: User,
    ) -> list[WorkflowRecoveryAction]:
        RecoveryService._lock_workflow(db, workflow_id, user, False)
        actions = db.scalars(
            select(WorkflowRecoveryAction)
            .where(WorkflowRecoveryAction.workflow_id == workflow_id)
            .order_by(WorkflowRecoveryAction.created_at.desc())
            .limit(100)
        ).all()
        db.rollback()
        return list(actions)

    @staticmethod
    def list_all(
        db: Session,
        user: User,
        status_filter: str | None,
        limit: int,
    ) -> list[WorkflowRecoveryAction]:
        """Recovery actions across workflows: all for admins, otherwise
        only those on the user's own workflows."""
        query = (
            select(WorkflowRecoveryAction)
            .order_by(WorkflowRecoveryAction.created_at.desc())
            .limit(limit)
        )

        if status_filter is not None:
            query = query.where(WorkflowRecoveryAction.status == status_filter)

        if not _is_admin(user):
            query = query.join(
                Workflow,
                Workflow.id == WorkflowRecoveryAction.workflow_id,
            ).join(Order, Order.id == Workflow.order_id).where(
                Order.user_id == user.id
            )

        actions = list(db.scalars(query).all())
        db.rollback()
        return actions

    # ------------------------------------------------------------ request
    @staticmethod
    def request(
        db: Session,
        workflow_id: UUID,
        user: User,
        action_type: RecoveryActionType,
        reason: str,
        idempotency_key: str | None,
        investigation_id: UUID | None = None,
    ) -> WorkflowRecoveryAction:
        key = idempotency_key or uuid.uuid4().hex
        workflow = RecoveryService._lock_workflow(
            db, workflow_id, user, owner_only=False
        )

        existing = db.scalar(
            select(WorkflowRecoveryAction).where(
                WorkflowRecoveryAction.workflow_id == workflow_id,
                WorkflowRecoveryAction.idempotency_key == key,
            )
        )

        if existing is not None:
            same = (
                existing.action_type == action_type.value
                and existing.reason == reason
            )
            db.rollback()
            if not same:
                raise _fail(
                    409,
                    "Idempotency key already used with a "
                    "different request",
                )
            return existing

        RecoveryService._validate_policy(db, workflow, action_type.value)

        if investigation_id is not None:
            investigation = db.get(Investigation, investigation_id)

            if (
                investigation is None
                or investigation.workflow_id != workflow_id
                or investigation.status != "completed"
            ):
                db.rollback()
                raise _fail(404, "Investigation not found for this workflow")

            if investigation.recommended_action != action_type.value:
                db.rollback()
                raise _fail(
                    409,
                    "Requested action does not match the "
                    "investigation's recommendation",
                )

        active = db.scalar(
            select(WorkflowRecoveryAction.id).where(
                WorkflowRecoveryAction.workflow_id == workflow_id,
                WorkflowRecoveryAction.status.in_(
                    [s.value for s in ACTIVE_RECOVERY_STATUSES]
                ),
            )
        )

        if active is not None:
            db.rollback()
            raise _fail(
                409,
                "Another recovery action is already active "
                "for this workflow",
            )

        action = WorkflowRecoveryAction(
            workflow_id=workflow.id,
            requested_by=user.id,
            investigation_id=investigation_id,
            action_type=action_type.value,
            status=S.REQUESTED.value,
            idempotency_key=key,
            reason=reason,
        )
        db.add(action)
        db.flush()

        RecoveryService._event(
            db,
            workflow,
            "recovery_requested",
            {
                "recovery_action_id": str(action.id),
                "action_type": action_type.value,
                "requested_by": str(user.id),
                "reason": reason,
            },
        )

        try:
            db.commit()
        except IntegrityError:
            # Lost a race against another active request (partial
            # unique index) or the same idempotency key.
            db.rollback()
            raise _fail(
                409,
                "Another recovery action is already active "
                "for this workflow",
            ) from None

        db.refresh(action)
        return action

    # ------------------------------------------------- approve / reject
    @staticmethod
    def approve(
        db: Session,
        workflow_id: UUID,
        action_id: UUID,
        approver: User,
    ) -> WorkflowRecoveryAction:
        if not _is_admin(approver):
            raise _fail(403, "Administrator role required")

        workflow = RecoveryService._lock_workflow(
            db, workflow_id, approver, owner_only=False
        )
        action = RecoveryService._lock_action(db, workflow_id, action_id)

        if action.status != S.REQUESTED.value:
            current = action.status
            db.rollback()
            raise _fail(409, f"Recovery action is already {current}")

        if action.requested_by == approver.id:
            db.rollback()
            raise _fail(
                403, "You cannot approve your own recovery request"
            )

        RecoveryService._validate_policy(db, workflow, action.action_type)
        RecoveryService._transition(action, S.APPROVED)
        action.approved_by = approver.id
        action.approved_at = _now()

        RecoveryService._event(
            db,
            workflow,
            "recovery_approved",
            {
                "recovery_action_id": str(action.id),
                "approved_by": str(approver.id),
            },
        )
        db.commit()
        db.refresh(action)
        return action

    @staticmethod
    def reject(
        db: Session,
        workflow_id: UUID,
        action_id: UUID,
        approver: User,
        reason: str,
    ) -> WorkflowRecoveryAction:
        if not _is_admin(approver):
            raise _fail(403, "Administrator role required")

        workflow = RecoveryService._lock_workflow(
            db, workflow_id, approver, owner_only=False
        )
        action = RecoveryService._lock_action(db, workflow_id, action_id)

        if action.status != S.REQUESTED.value:
            current = action.status
            db.rollback()
            raise _fail(409, f"Recovery action is already {current}")

        RecoveryService._transition(action, S.REJECTED)
        action.rejected_by = approver.id
        action.rejected_at = _now()
        action.rejection_reason = reason

        RecoveryService._event(
            db,
            workflow,
            "recovery_rejected",
            {
                "recovery_action_id": str(action.id),
                "rejected_by": str(approver.id),
                "reason": reason,
            },
        )
        db.commit()
        db.refresh(action)
        return action

    # ------------------------------------------------------------- queue
    @staticmethod
    def queue_execution(
        db: Session,
        workflow_id: UUID,
        action_id: UUID,
        user: User,
    ) -> WorkflowRecoveryAction:
        workflow = RecoveryService._lock_workflow(
            db, workflow_id, user, owner_only=False
        )
        action = RecoveryService._lock_action(db, workflow_id, action_id)

        # Repeating the call must not queue a second execution.
        if action.status in (
            S.QUEUED.value, S.EXECUTING.value, S.EXECUTED.value,
        ):
            db.rollback()
            return action

        if action.status != S.APPROVED.value:
            current = action.status
            db.rollback()
            raise _fail(
                409,
                f"Only an approved recovery can be executed "
                f"(currently {current})",
            )

        RecoveryService._validate_policy(db, workflow, action.action_type)
        RecoveryService._transition(action, S.QUEUED)

        OutboxPublisher.add(
            db,
            OutboxEventType.RECOVERY_EXECUTE,
            action.id,
            {"recovery_action_id": str(action.id)},
        )
        RecoveryService._event(
            db,
            workflow,
            "recovery_queued",
            {"recovery_action_id": str(action.id)},
        )
        db.commit()
        db.refresh(action)
        return action

    # ----------------------------------------------------------- execute
    @staticmethod
    def execute(db: Session, action_id: UUID) -> None:
        """Worker entry point. Safe under duplicate delivery: an action
        that is finished or leased by another worker is left alone."""
        token = uuid.uuid4().hex

        # 1. Claim (short transaction, lease).
        action = db.scalar(
            select(WorkflowRecoveryAction)
            .where(WorkflowRecoveryAction.id == action_id)
            .with_for_update()
        )

        if action is None:
            db.rollback()
            return

        now = _now()

        if action.status == S.QUEUED.value:
            RecoveryService._transition(action, S.EXECUTING)
        elif not (
            action.status == S.EXECUTING.value
            and action.claim_expires_at is not None
            and action.claim_expires_at <= now
        ):
            # Finished, not yet approved/queued, or leased elsewhere.
            db.rollback()
            return

        action.claim_token = token
        action.claim_expires_at = now + EXECUTION_LEASE
        workflow_id = action.workflow_id
        action_type = RecoveryActionType(action.action_type)
        db.commit()

        # 2. Perform, re-validating against live state.
        try:
            RecoveryService._perform(db, workflow_id, action_id, action_type)
        except Exception as exc:
            db.rollback()
            RecoveryService._settle(
                db, action_id, token, error=str(exc)[:1000]
            )
            return

        # 3. Settle.
        RecoveryService._settle(db, action_id, token)

    @staticmethod
    def _perform(
        db: Session,
        workflow_id: UUID,
        action_id: UUID,
        action_type: RecoveryActionType,
    ) -> None:
        if action_type == RecoveryActionType.RECONCILE_AND_RESUME:
            workflow = db.get(Workflow, workflow_id)
            try:
                RecoveryPolicy.validate(
                    workflow.status,
                    workflow.last_error_code,
                    action_type,
                    workflow.current_step,
                )
            except ValueError:
                db.rollback()
                # Already reconciled by an earlier (crashed) run?
                if workflow.status == "completed" or (
                    workflow.current_step != "reserve_inventory"
                    and workflow.last_error_code is None
                ):
                    return
                raise
            db.rollback()

            try:
                result = ReconciliationService.reconcile_reservation(
                    db, workflow_id
                )
            except (ReconciliationNotAllowed, ReconciliationConflict) as exc:
                raise RecoveryExecutionError(str(exc)) from exc

            if not result.reservation_found:
                raise RecoveryExecutionError(
                    "No matching reservation was found; the workflow "
                    "stays in review"
                )
            return

        if action_type == RecoveryActionType.RELEASE_RESERVATION:
            RecoveryService._release_reservation(db, workflow_id, action_id)
            return

        workflow = db.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .with_for_update()
        )

        try:
            RecoveryPolicy.validate(
                workflow.status,
                workflow.last_error_code,
                action_type,
                workflow.current_step,
                RecoveryService._reservation_status(db, workflow.order_id),
            )
        except ValueError as exc:
            raise RecoveryExecutionError(str(exc)) from exc

        if action_type == RecoveryActionType.RETRY_WORKFLOW:
            # One operator-approved execution. The automatic retry
            # budget is NOT reset: attempts keeps counting, so another
            # transient failure ends in `failed` again.
            workflow.status = "pending"
            workflow.next_retry_at = None
            workflow.version += 1
            order = db.get(Order, workflow.order_id)
            if order is not None:
                order.status = "processing"

            RecoveryService._event(
                db, workflow, "workflow_resumed",
                {"recovery_action_id": str(action_id)},
            )
            OutboxPublisher.add(
                db,
                OutboxEventType.WORKFLOW_RESUME,
                workflow.id,
                {"workflow_id": str(workflow.id)},
            )

        elif action_type == RecoveryActionType.MARK_FOR_REVIEW:
            if workflow.status == "failed":
                workflow.status = "needs_review"
                workflow.version += 1

            RecoveryService._event(
                db, workflow, "marked_for_review",
                {"recovery_action_id": str(action_id)},
            )

        db.commit()

    @staticmethod
    def _release_reservation(
        db: Session,
        workflow_id: UUID,
        action_id: UUID,
    ) -> None:
        """Compensation: release the order's reserved stock and close the
        workflow as `compensated`.

        Three short transactions, mirroring the reserve step: prepare,
        call the provider with no lock held, settle. Releasing is
        idempotent, so a run that crashed midway can simply be repeated.
        """
        # 1. Prepare
        workflow = db.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .with_for_update()
        )
        order = db.get(Order, workflow.order_id)

        if workflow.status == "compensated":
            # An earlier run finished the compensation before crashing.
            db.rollback()
            return

        try:
            RecoveryPolicy.validate(
                workflow.status,
                workflow.last_error_code,
                RecoveryActionType.RELEASE_RESERVATION,
                workflow.current_step,
                RecoveryService._reservation_status(db, order.id),
            )
        except ValueError as exc:
            raise RecoveryExecutionError(str(exc)) from exc

        key = f"release:{order.id}"
        operation = db.scalar(
            select(WorkflowOperation)
            .where(WorkflowOperation.operation_key == key)
            .with_for_update()
        )

        if operation is None:
            operation = WorkflowOperation(
                workflow_id=workflow.id,
                operation_key=key,
                # The step being compensated.
                step="reserve_inventory",
                status="pending",
                attempts=0,
            )
            db.add(operation)
            db.flush()

        operation.status = "pending"
        operation.attempts += 1

        RecoveryService._event(
            db, workflow, "compensation_started",
            {
                "recovery_action_id": str(action_id),
                "operation_key": key,
            },
        )
        order_id = order.id
        db.commit()

        # 2. Provider call (no transaction held)
        try:
            reservation_id = SimulatedInventoryProvider.release(order_id)
        except Exception as exc:
            db.rollback()
            operation = db.scalar(
                select(WorkflowOperation).where(
                    WorkflowOperation.operation_key == key
                )
            )
            operation.status = "failed"
            operation.last_error_code = type(exc).__name__[:100]
            db.commit()
            raise RecoveryExecutionError(
                f"Release did not complete ({exc}). Releasing is "
                "idempotent, so it is safe to request it again."
            ) from exc

        if reservation_id is None:
            raise RecoveryExecutionError(
                "No reservation exists for this order, nothing to release"
            )

        # 3. Settle
        workflow = db.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .with_for_update()
        )
        order = db.get(Order, workflow.order_id)
        operation = db.scalar(
            select(WorkflowOperation)
            .where(WorkflowOperation.operation_key == key)
            .with_for_update()
        )
        operation.status = "confirmed"
        operation.external_reference = reservation_id
        operation.last_error_code = None

        # The original reservation operation no longer describes reality.
        reserve_operation = db.scalar(
            select(WorkflowOperation)
            .where(
                WorkflowOperation.operation_key == f"reserve:{order.id}"
            )
            .with_for_update()
        )
        if reserve_operation is not None and reserve_operation.status in (
            "uncertain",
            "pending",
        ):
            reserve_operation.status = "failed"
            reserve_operation.last_error_code = "COMPENSATED"
            reserve_operation.claim_token = None
            reserve_operation.claim_expires_at = None

        original_error = workflow.last_error_code
        workflow.status = "compensated"
        workflow.next_retry_at = None
        workflow.version += 1
        order.status = "cancelled"

        RecoveryService._event(
            db, workflow, "reservation_released",
            {"reservation_id": reservation_id},
        )
        RecoveryService._event(
            db, workflow, "workflow_compensated",
            {
                "recovery_action_id": str(action_id),
                "original_error": original_error,
            },
        )
        db.commit()

    @staticmethod
    def _settle(
        db: Session,
        action_id: UUID,
        token: str,
        error: str | None = None,
    ) -> None:
        action = db.scalar(
            select(WorkflowRecoveryAction)
            .where(WorkflowRecoveryAction.id == action_id)
            .with_for_update()
        )

        if (
            action is None
            or action.status != S.EXECUTING.value
            or action.claim_token != token
        ):
            # Lease lost to another worker; it will settle the action.
            db.rollback()
            return

        workflow = db.get(Workflow, action.workflow_id)

        if error is None:
            RecoveryService._transition(action, S.EXECUTED)
            action.executed_at = _now()
            event = "recovery_executed"
            details = {"recovery_action_id": str(action.id)}
        else:
            RecoveryService._transition(action, S.FAILED)
            action.error_message = error
            event = "recovery_failed"
            details = {
                "recovery_action_id": str(action.id),
                "error": error,
            }

        action.claim_token = None
        action.claim_expires_at = None

        if workflow is not None:
            RecoveryService._event(db, workflow, event, details)

        db.commit()
