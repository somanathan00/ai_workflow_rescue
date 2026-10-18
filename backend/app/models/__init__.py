
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    FeedbackRating,
    InvestigationStatus,
    OperationStatus,
    OrderStatus,
    OutboxStatus,
    RecommendedAction,
    RecoveryActionStatus,
    RecoveryActionType,
    ReservationStatus,
    UserRole,
    WorkflowStatus,
    WorkflowStep,
)
from app.infrastructure.database.base import Base


def _in(column: str, enum_cls) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return f"{column} IN ({values})"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint(
            "username ~ '^[a-z0-9_]{3,30}$'", name="username_format",
        ),
        CheckConstraint(_in("role", UserRole), name="role_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default=UserRole.OPERATOR.value,
        server_default=UserRole.OPERATOR.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        server_default=text("true"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    orders: Mapped[list["Order"]] = relationship(
        back_populates="user", passive_deletes=True,
    )


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key",
            name="uq_order_user_idempotency",
        ),
        CheckConstraint(
            "quantity > 0", name="quantity_positive",
        ),
        CheckConstraint(_in("status", OrderStatus), name="status_valid"),
        CheckConstraint(
            "length(trim(product_id)) > 0", name="product_id_not_blank",
        ),
        CheckConstraint(
            "length(trim(idempotency_key)) > 0",
            name="idempotency_key_not_blank",
        ),
        Index("ix_order_user_created", "user_id", "created_at"),
        Index("ix_order_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False,
    )
    request_hash: Mapped[str] = mapped_column(
        String(64), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default=OrderStatus.PENDING.value,
        server_default=OrderStatus.PENDING.value,
    )

    user: Mapped["User"] = relationship(
        back_populates="orders",
    )
    workflow: Mapped["Workflow"] = relationship(
        back_populates="order", uselist=False,
    )
    reservation: Mapped["InventoryReservation"] = relationship(
        back_populates="order", uselist=False,
    )
    invoice: Mapped["Invoice"] = relationship(
        back_populates="order", uselist=False,
    )


class Workflow(TimestampMixin, Base):
    __tablename__ = "workflows"
    __table_args__ = (
        Index("ix_workflow_status_created", "status", "created_at"),
        Index(
            "ix_workflow_retry_due", "next_retry_at",
            postgresql_where=text("status = 'retry_scheduled'"),
        ),
        CheckConstraint(_in("status", WorkflowStatus), name="status_valid"),
        CheckConstraint(
            f"current_step IS NULL OR {_in('current_step', WorkflowStep)}",
            name="current_step_valid",
        ),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default=WorkflowStatus.PENDING.value,
        server_default=WorkflowStatus.PENDING.value,
    )
    current_step: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"),
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(100),
    )
    last_error_message: Mapped[str | None] = mapped_column(
        Text,
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1"),
    )

    order: Mapped["Order"] = relationship(
        back_populates="workflow",
    )
    operations: Mapped[list["WorkflowOperation"]] = relationship(
        back_populates="workflow", passive_deletes=True,
    )
    events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="workflow", passive_deletes=True,
    )
    investigations: Mapped[list["Investigation"]] = relationship(
        back_populates="workflow", passive_deletes=True,
    )
    recovery_actions: Mapped[list["WorkflowRecoveryAction"]] = (
        relationship(back_populates="workflow", passive_deletes=True)
    )


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (
        Index(
            "ix_event_workflow_created",
            "workflow_id", "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False,
    )
    step: Mapped[str | None] = mapped_column(
        String(50),
    )
    event_type: Mapped[str] = mapped_column(
        String(80), nullable=False,
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(), nullable=False,
    )

    workflow: Mapped["Workflow"] = relationship(
        back_populates="events",
    )


class InventoryReservation(TimestampMixin, Base):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="quantity_positive",
        ),
        CheckConstraint(
            _in("status", ReservationStatus), name="status_valid",
        ),
        Index("ix_reservation_product_status", "product_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default=ReservationStatus.RESERVED.value,
        server_default=ReservationStatus.RESERVED.value,
    )

    order: Mapped["Order"] = relationship(
        back_populates="reservation",
    )


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('generated', 'void')", name="status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default="generated", server_default="generated",
    )

    order: Mapped["Order"] = relationship(
        back_populates="invoice",
    )


class Investigation(TimestampMixin, Base):
    __tablename__ = "investigations"
    __table_args__ = (
        CheckConstraint(
            _in("status", InvestigationStatus), name="status_valid",
        ),
        CheckConstraint(
            f"recommended_action IS NULL OR "
            f"{_in('recommended_action', RecommendedAction)}",
            name="recommended_action_valid",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        Index("ix_investigation_workflow_created", "workflow_id", "created_at"),
        # One in-flight investigation per workflow.
        Index(
            "uq_active_investigation_per_workflow", "workflow_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default=InvestigationStatus.PENDING.value,
        server_default=InvestigationStatus.PENDING.value,
    )
    root_cause: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(
        String(50),
    )
    reasoning: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list,
        server_default=text("'[]'::jsonb"),
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    policy_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    model_name: Mapped[str | None] = mapped_column(
        String(100),
    )
    prompt_version: Mapped[str | None] = mapped_column(
        String(30),
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        server_default=text("true"),
    )

    workflow: Mapped["Workflow"] = relationship(
        back_populates="investigations",
    )


class WorkflowRecoveryAction(TimestampMixin, Base):
    __tablename__ = "workflow_recovery_actions"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id", "idempotency_key",
            name="uq_recovery_idempotency",
        ),
        CheckConstraint(
            _in("action_type", RecoveryActionType),
            name="action_type_valid",
        ),
        CheckConstraint(
            _in("status", RecoveryActionStatus), name="status_valid",
        ),
        # At most one active recovery per workflow, enforced by the
        # database so concurrent requests cannot both succeed.
        Index(
            "uq_active_recovery_per_workflow", "workflow_id",
            unique=True,
            postgresql_where=text(
                "status IN ('requested', 'approved', "
                "'queued', 'executing')"
            ),
        ),
        Index("ix_recovery_workflow_created", "workflow_id", "created_at"),
        Index("ix_recovery_requested_by", "requested_by"),
        Index("ix_recovery_investigation", "investigation_id"),
        Index(
            "ix_recovery_stale_lease", "claim_expires_at",
            postgresql_where=text("status = 'executing'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False,
    )
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="SET NULL"),
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    action_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default=RecoveryActionStatus.REQUESTED.value,
        server_default=RecoveryActionStatus.REQUESTED.value,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    claim_token: Mapped[str | None] = mapped_column(String(64))
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    workflow: Mapped["Workflow"] = relationship(
        back_populates="recovery_actions",
    )


class WorkflowOperation(TimestampMixin, Base):
    """A side-effecting business operation, identified by a stable key.

    The key (for example ``reserve:<order_id>``) is reused on every
    attempt so the external provider can deduplicate. ``claim_token`` and
    ``claim_expires_at`` are a lease: only the worker holding an unexpired
    lease may call the provider and settle the operation.
    """

    __tablename__ = "workflow_operations"
    __table_args__ = (
        UniqueConstraint(
            "operation_key", name="uq_workflow_operation_key",
        ),
        CheckConstraint(
            _in("status", OperationStatus), name="status_valid",
        ),
        CheckConstraint(
            f"step IS NOT NULL AND {_in('step', WorkflowStep)}",
            name="step_valid",
        ),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_operation_workflow_step", "workflow_id", "step"),
        Index(
            "ix_operation_uncertain", "workflow_id",
            postgresql_where=text("status = 'uncertain'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False,
    )
    operation_key: Mapped[str] = mapped_column(
        String(200), nullable=False,
    )
    step: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default=OperationStatus.PENDING.value,
        server_default=OperationStatus.PENDING.value,
    )
    external_reference: Mapped[str | None] = mapped_column(
        String(200),
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"),
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(100),
    )
    claim_token: Mapped[str | None] = mapped_column(
        String(64),
    )
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    workflow: Mapped["Workflow"] = relationship(
        back_populates="operations",
    )


class OutboxMessage(Base):
    """Message written in the same transaction as the state change that
    caused it, then delivered to Celery by the dispatcher (at-least-once).

    ``claim_token`` / ``claimed_until`` let several dispatchers share the
    table: a claim that is not settled before it expires is retried.
    """

    __tablename__ = "outbox_messages"
    __table_args__ = (
        CheckConstraint(_in("status", OutboxStatus), name="status_valid"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index(
            "ix_outbox_due", "next_attempt_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_outbox_aggregate", "aggregate_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    aggregate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default=OutboxStatus.PENDING.value,
        server_default=OutboxStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"),
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), nullable=False,
    )
    claim_token: Mapped[str | None] = mapped_column(String(64))
    claimed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(), nullable=False,
    )


class InvestigationFeedback(TimestampMixin, Base):
    """A person's verdict on whether an AI investigation was useful.
    One row per (investigation, user); changing your mind updates it."""

    __tablename__ = "investigation_feedback"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id", "user_id",
            name="uq_feedback_investigation_user",
        ),
        CheckConstraint(_in("rating", FeedbackRating), name="rating_valid"),
        Index("ix_feedback_investigation", "investigation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    rating: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
