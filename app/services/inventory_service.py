
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InventoryReservation, Order


class InventoryService:

    @staticmethod
    def reserve(
        db: Session,
        order: Order,
    ) -> InventoryReservation:
        existing = db.scalar(
            select(InventoryReservation).where(
                InventoryReservation.order_id == order.id
            )
        )

        if existing is not None:
            if (
                existing.product_id != order.product_id
                or existing.quantity != order.quantity
            ):
                raise ValueError(
                    "Existing reservation does not match order"
                )

            if existing.status != "reserved":
                raise ValueError(
                    "Existing reservation is not active"
                )

            return existing

        reservation = InventoryReservation(
            order_id=order.id,
            product_id=order.product_id,
            quantity=order.quantity,
            status="reserved",
        )

        db.add(reservation)
        db.flush()

        return reservation
