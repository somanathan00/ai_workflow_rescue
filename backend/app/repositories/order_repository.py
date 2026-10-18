
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Workflow


class OrderRepository:

    @staticmethod
    def get_by_idempotency_key(
        db: Session,
        user_id: UUID,
        key: str,
    ) -> Order | None:
        return db.scalar(
            select(Order).where(
                Order.user_id == user_id,
                Order.idempotency_key == key,
            )
        )

    @staticmethod
    def get_by_id(
        db: Session,
        order_id: UUID,
        user_id: UUID,
    ) -> Order | None:
        return db.scalar(
            select(Order).where(
                Order.id == order_id,
                Order.user_id == user_id,
            )
        )

    @staticmethod
    def get_workflow(
        db: Session,
        order_id: UUID,
    ) -> Workflow | None:
        return db.scalar(
            select(Workflow).where(
                Workflow.order_id == order_id
            )
        )
