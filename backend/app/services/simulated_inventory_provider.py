from uuid import UUID

from sqlalchemy import select

from app.domain.exceptions import UncertainOutcomeError
from app.infrastructure.database.session import SessionLocal
from app.models import InventoryReservation


class SimulatedInventoryProvider:
    """Stand-in for an external inventory system.

    It works in its own session and transaction, so a reservation commits
    independently of the workflow's transaction. That is what lets us
    simulate "the side effect happened but the response was lost".
    """

    @staticmethod
    def reserve(
        order_id: UUID,
        product_id: str,
        quantity: int,
        simulate_lost_response: bool = False,
    ) -> str:
        # Idempotent: a repeated call for the same order returns the
        # existing reservation. ``order_id`` (unique on the table) plays
        # the role of the provider-side idempotency key.
        with SessionLocal.begin() as db:
            reservation = db.scalar(
                select(InventoryReservation).where(
                    InventoryReservation.order_id == order_id
                )
            )

            if reservation is None:
                reservation = InventoryReservation(
                    order_id=order_id,
                    product_id=product_id,
                    quantity=quantity,
                    status="reserved",
                )
                db.add(reservation)
                db.flush()

            elif (
                reservation.product_id != product_id
                or reservation.quantity != quantity
                or reservation.status != "reserved"
            ):
                raise ValueError(
                    "Existing reservation conflicts with "
                    "requested reservation"
                )

            reservation_id = str(reservation.id)

        # The transaction has committed; only the response is lost.
        if simulate_lost_response:
            raise UncertainOutcomeError(
                "Inventory reservation may have succeeded, "
                "but the response was lost"
            )

        return reservation_id

    @staticmethod
    def release(order_id: UUID) -> str | None:
        """Compensation: give the reserved stock back.

        Idempotent, in its own transaction like ``reserve``. Returns the
        reservation id, or None when the order never had a reservation.
        Repeating the call after it succeeded changes nothing.
        """
        with SessionLocal.begin() as db:
            reservation = db.scalar(
                select(InventoryReservation).where(
                    InventoryReservation.order_id == order_id
                )
            )

            if reservation is None:
                return None

            if reservation.status != "released":
                reservation.status = "released"

            return str(reservation.id)
