from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WorkflowOperation


def lookup_operations(db: Session, workflow_id: UUID) -> list[dict]:
    """State of the workflow's side-effecting operations. Read-only."""
    now = datetime.now(UTC)
    operations = db.scalars(
        select(WorkflowOperation)
        .where(WorkflowOperation.workflow_id == workflow_id)
        .order_by(WorkflowOperation.created_at.asc())
    ).all()

    return [
        {
            "ref": f"operation:{op.operation_key}",
            "step": op.step,
            "status": op.status,
            "attempts": op.attempts,
            "last_error_code": op.last_error_code,
            "has_external_reference": op.external_reference is not None,
            "lease_active": bool(
                op.claim_expires_at and op.claim_expires_at > now
            ),
        }
        for op in operations
    ]
