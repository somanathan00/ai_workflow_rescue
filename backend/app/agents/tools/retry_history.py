from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.policies.retry_policy import RetryPolicy
from app.models import Workflow, WorkflowEvent


def get_retry_history(db: Session, workflow_id: UUID) -> dict:
    """Failures and retries recorded so far. Read-only."""
    counts = dict(
        db.execute(
            select(WorkflowEvent.event_type, func.count())
            .where(
                WorkflowEvent.workflow_id == workflow_id,
                WorkflowEvent.event_type.in_(
                    ["step_failed", "retry_scheduled", "retry_started"]
                ),
            )
            .group_by(WorkflowEvent.event_type)
        ).all()
    )
    workflow = db.get(Workflow, workflow_id)

    return {
        "ref": f"retry_history:{workflow_id}",
        "failed_steps": counts.get("step_failed", 0),
        "retries_scheduled": counts.get("retry_scheduled", 0),
        "retries_started": counts.get("retry_started", 0),
        "attempts": workflow.attempts if workflow else 0,
        "max_attempts": RetryPolicy.MAX_ATTEMPTS,
        "budget_exhausted": bool(
            workflow and workflow.attempts >= RetryPolicy.MAX_ATTEMPTS
        ),
    }
