
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invoice, Order


class InvoiceService:

    @staticmethod
    def generate(
        db: Session,
        order: Order,
    ) -> Invoice:
        existing = db.scalar(
            select(Invoice).where(
                Invoice.order_id == order.id
            )
        )

        if existing is not None:
            return existing

        invoice = Invoice(
            order_id=order.id,
            invoice_number=f"INV-{order.id.hex[:20].upper()}",
            status="generated",
        )

        db.add(invoice)
        db.flush()

        return invoice
