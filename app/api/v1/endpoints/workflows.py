
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, DBSession
from app.models import Order, Workflow, WorkflowEvent
from app.schemas.workflow import (
    WorkflowEventResponse,
    WorkflowResponse,
)


router = APIRouter(
    prefix="/workflows",
    tags=["Workflows"],
)


def get_authorized_workflow(
    db: Session,
    workflow_id: UUID,
    user_id: UUID,
) -> Workflow:
    workflow = db.scalar(
        select(Workflow)
        .join(Order, Workflow.order_id == Order.id)
        .where(
            Workflow.id == workflow_id,
            Order.user_id == user_id,
        )
    )

    if workflow is None:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found",
        )

    return workflow


@router.get(
    "/failed",
    response_model=list[WorkflowResponse],
)
def list_failed_workflows(
    db: DBSession,
    current_user: CurrentUser,
):
    return db.scalars(
        select(Workflow)
        .join(Order, Workflow.order_id == Order.id)
        .where(
            Order.user_id == current_user.id,
            Workflow.status == "failed",
        )
        .order_by(Workflow.created_at.desc())
        .limit(100)
    ).all()


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
)
def get_workflow(
    workflow_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    return get_authorized_workflow(
        db, workflow_id, current_user.id
    )


@router.get(
    "/{workflow_id}/events",
    response_model=list[WorkflowEventResponse],
)
def get_workflow_events(
    workflow_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    get_authorized_workflow(
        db, workflow_id, current_user.id
    )

    return db.scalars(
        select(WorkflowEvent)
        .where(
            WorkflowEvent.workflow_id == workflow_id
        )
        .order_by(
            WorkflowEvent.created_at.asc(),
            WorkflowEvent.id.asc(),
        )
        .limit(500)
    ).all()
