
from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"


class OrderStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"


class WorkflowStep(StrEnum):
    VALIDATE_ORDER = "validate_order"
    RESERVE_INVENTORY = "reserve_inventory"
    GENERATE_INVOICE = "generate_invoice"


class ReservationStatus(StrEnum):
    RESERVED = "reserved"
    RELEASED = "released"


class InvestigationStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class RecoveryAction(StrEnum):
    RETRY = "retry"
    MANUAL_REVIEW = "manual_review"
    NO_ACTION = "no_action"


class RecoveryStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
