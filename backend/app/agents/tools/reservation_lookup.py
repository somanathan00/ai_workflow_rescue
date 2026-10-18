from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InventoryReservation, Order


def lookup_reservation(db: Session, order_id: UUID) -> dict:
    """Whether the order has an inventory reservation, from the database
    (never inferred from an error message). Read-only."""
    order = db.get(Order, order_id)
    reservation = db.scalar(
        select(InventoryReservation).where(
            InventoryReservation.order_id == order_id
        )
    )

    if reservation is None:
        return {
            "ref": f"reservation:none:{order_id}",
            "exists": False,
        }

    return {
        "ref": f"reservation:{reservation.id}",
        "exists": True,
        "status": reservation.status,
        "matches_order": (
            order is not None
            and reservation.product_id == order.product_id
            and reservation.quantity == order.quantity
        ),
    }
