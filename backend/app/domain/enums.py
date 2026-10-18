
from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"


class OrderStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    # Failed and its side effects were undone (stock released).
    COMPENSATED = "compensated"


class WorkflowStep(StrEnum):
    VALIDATE_ORDER = "validate_order"
    RESERVE_INVENTORY = "reserve_inventory"
    GENERATE_INVOICE = "generate_invoice"


class ReservationStatus(StrEnum):
    RESERVED = "reserved"
    RELEASED = "released"


class OperationStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"
    FAILED = "failed"


class InvestigationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RecommendedAction(StrEnum):
    """What the investigator may recommend. The first three map one to
    one onto RecoveryActionType, so a recommendation can only ever be
    carried out through the approved recovery APIs."""

    RETRY_WORKFLOW = "retry_workflow"
    RECONCILE_AND_RESUME = "reconcile_and_resume"
    MARK_FOR_REVIEW = "mark_for_review"
    RELEASE_RESERVATION = "release_reservation"
    NO_ACTION = "no_action"


class RecoveryActionType(StrEnum):
    RETRY_WORKFLOW = "retry_workflow"
    RECONCILE_AND_RESUME = "reconcile_and_resume"
    MARK_FOR_REVIEW = "mark_for_review"
    # Compensation: undo the inventory reservation of an order that cannot
    # (or should not) complete.
    RELEASE_RESERVATION = "release_reservation"


class RecoveryActionStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    QUEUED = "queued"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"


# Statuses in which a recovery action still owns the workflow.
ACTIVE_RECOVERY_STATUSES = (
    RecoveryActionStatus.REQUESTED,
    RecoveryActionStatus.APPROVED,
    RecoveryActionStatus.QUEUED,
    RecoveryActionStatus.EXECUTING,
)


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    DEAD = "dead"


class OutboxEventType(StrEnum):
    WORKFLOW_START = "workflow.start"
    WORKFLOW_RESUME = "workflow.resume"
    RECOVERY_EXECUTE = "recovery.execute"
    INVESTIGATION_START = "investigation.start"


class FeedbackRating(StrEnum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
