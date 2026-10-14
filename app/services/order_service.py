
import hashlib
import json
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Order,
    Workflow,
    WorkflowEvent,
)
from app.repositories.order_repository import (
    OrderRepository,
)
from app.schemas.order import OrderCreate


class OrderService:

    @staticmethod
    def request_hash(payload: OrderCreate) -> str:
        serialized = json.dumps(
            payload.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )

        return hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def create_order(
        db: Session,
        user_id: UUID,
        payload: OrderCreate,
        idempotency_key: str,
    ) -> tuple[Order, bool]:

        payload_hash = OrderService.request_hash(payload)

        existing = OrderRepository.get_by_idempotency_key(
            db, user_id, idempotency_key
        )

        if existing:
            if existing.request_hash != payload_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Idempotency key already used "
                        "with a different request"
                    ),
                )

            return existing, False

        order = Order(
            user_id=user_id,
            product_id=payload.product_id,
            quantity=payload.quantity,
            idempotency_key=idempotency_key,
            request_hash=payload_hash,
            status="pending",
        )

        workflow = Workflow(
            order=order,
            status="pending",
            current_step="validate_order",
            attempts=0,
        )

        event = WorkflowEvent(
            workflow=workflow,
            step="validate_order",
            event_type="workflow_created",
            details={
                "message": "Order accepted for processing"
            },
        )

        db.add_all([order, workflow, event])

        try:
            db.commit()
            db.refresh(order)
            return order, True

        except IntegrityError:
            db.rollback()

            # Another concurrent request may have
            # created the same idempotency key.
            existing = OrderRepository.get_by_idempotency_key(
                db, user_id, idempotency_key
            )

            if existing is not None:
                if existing.request_hash != payload_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key conflict",
                    )

                return existing, False

            # An unrelated database constraint failed.
            # Do not disguise it as an idempotency conflict.
            raise
