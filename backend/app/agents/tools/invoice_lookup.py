from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invoice


def lookup_invoice(db: Session, order_id: UUID) -> dict:
    """Whether an invoice exists for the order. Read-only."""
    invoice = db.scalar(
        select(Invoice).where(Invoice.order_id == order_id)
    )

    if invoice is None:
        return {"ref": f"invoice:none:{order_id}", "exists": False}

    return {
        "ref": f"invoice:{invoice.id}",
        "exists": True,
        "status": invoice.status,
    }
