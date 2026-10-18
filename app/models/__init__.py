
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
    func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    InvestigationStatus, OrderStatus, RecoveryAction, RecoveryStatus,
    ReservationStatus, UserRole, WorkflowStatus, WorkflowStep,
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
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1"),
    )

    order: Mapped["Order"] = relationship(
        back_populates="workflow",
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
        server_default=func.now(), nullable=False,
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
            f"{_in('recommended_action', RecoveryAction)}",
            name="recommended_action_valid",
        ),
        Index("ix_investigation_workflow_created", "workflow_id", "created_at"),
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
        CheckConstraint(_in("action", RecoveryAction), name="action_valid"),
        CheckConstraint(_in("status", RecoveryStatus), name="status_valid"),
        Index("ix_recovery_workflow_created", "workflow_id", "created_at"),
        Index("ix_recovery_requested_by", "requested_by"),
        Index("ix_recovery_investigation", "investigation_id"),
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
    action: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default=RecoveryStatus.REQUESTED.value,
        server_default=RecoveryStatus.REQUESTED.value,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    workflow: Mapped["Workflow"] = relationship(
        back_populates="recovery_actions",
    )
