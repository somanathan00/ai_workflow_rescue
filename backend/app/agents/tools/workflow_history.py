from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Workflow, WorkflowEvent

MAX_EVENTS = 100


def get_workflow_history(db: Session, workflow_id: UUID) -> dict | None:
    """Workflow, its order and the ordered event log. Read-only."""
    workflow = db.get(Workflow, workflow_id)

    if workflow is None:
        return None

    order = db.get(Order, workflow.order_id)
    events = db.scalars(
        select(WorkflowEvent)
        .where(WorkflowEvent.workflow_id == workflow_id)
        .order_by(WorkflowEvent.created_at.asc(), WorkflowEvent.id.asc())
        .limit(MAX_EVENTS)
    ).all()

    return {
        "workflow": {
            "ref": f"workflow:{workflow.id}",
            "status": workflow.status,
            "current_step": workflow.current_step,
            "attempts": workflow.attempts,
            "last_error_code": workflow.last_error_code,
            "last_error_message": workflow.last_error_message,
            "next_retry_at": workflow.next_retry_at,
        },
        "order": {
            "ref": f"order:{order.id}",
            "product_id": order.product_id,
            "quantity": order.quantity,
            "status": order.status,
        },
        "events": [
            {
                "ref": f"event:{e.id}",
                "event_type": e.event_type,
                "step": e.step,
                "details": e.details,
                "created_at": e.created_at,
            }
            for e in events
        ],
    }
