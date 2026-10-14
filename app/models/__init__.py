
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey,
    Index, Integer, JSON, String, Text, UniqueConstraint,
    func, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(30), nullable=False, default="operator",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )

    orders: Mapped[list["Order"]] = relationship(
        back_populates="user",
    )


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key",
            name="uq_order_user_idempotency",
        ),
        CheckConstraint(
            "quantity > 0", name="ck_order_quantity_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True,
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
        String(30), nullable=False, default="pending",
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
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id"), unique=True, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending",
    )
    current_step: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(100),
    )
    last_error_message: Mapped[str | None] = mapped_column(
        Text,
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
    )

    order: Mapped["Order"] = relationship(
        back_populates="workflow",
    )
    events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="workflow",
    )
    investigations: Mapped[list["Investigation"]] = relationship(
        back_populates="workflow",
    )
    recovery_actions: Mapped[list["WorkflowRecoveryAction"]] = (
        relationship(back_populates="workflow")
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
        ForeignKey("workflows.id"), nullable=False,
    )
    step: Mapped[str | None] = mapped_column(
        String(50),
    )
    event_type: Mapped[str] = mapped_column(
        String(80), nullable=False,
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict,
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
            name="ck_reservation_quantity_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id"), unique=True, nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="reserved",
    )

    order: Mapped["Order"] = relationship(
        back_populates="reservation",
    )


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id"), unique=True, nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="generated",
    )

    order: Mapped["Order"] = relationship(
        back_populates="invoice",
    )


class Investigation(TimestampMixin, Base):
    __tablename__ = "investigations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id"), nullable=False, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending",
    )
    root_cause: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(
        String(50),
    )
    reasoning: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list,
    )
    model_name: Mapped[str | None] = mapped_column(
        String(100),
    )
    prompt_version: Mapped[str | None] = mapped_column(
        String(30),
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
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
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id"), nullable=False, index=True,
    )
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigations.id"),
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="requested",
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
