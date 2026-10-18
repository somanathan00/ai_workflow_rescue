
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, DBSession
from app.domain.enums import UserRole, WorkflowStatus
from app.models import (
    InventoryReservation,
    Invoice,
    Order,
    User,
    Workflow,
    WorkflowEvent,
)
from app.schemas.workflow import (
    ReconcileResponse,
    WorkflowEventResponse,
    WorkflowResponse,
    WorkflowSummary,
)
from app.services.reconciliation_service import (
    ReconciliationConflict,
    ReconciliationNotAllowed,
    ReconciliationService,
)

router = APIRouter(
    prefix="/workflows",
    tags=["Workflows"],
)


def get_authorized_workflow(
    db: Session,
    workflow_id: UUID,
    user: User,
) -> Workflow:
    """The workflow if the user owns it or is an admin; otherwise 404."""
    query = (
        select(Workflow)
        .join(Order, Workflow.order_id == Order.id)
        .where(Workflow.id == workflow_id)
    )

    if user.role != UserRole.ADMIN.value:
        query = query.where(Order.user_id == user.id)

    workflow = db.scalar(query)

    if workflow is None:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found",
        )

    return workflow


@router.get(
    "",
    response_model=list[WorkflowSummary],
)
def list_workflows(
    db: DBSession,
    current_user: CurrentUser,
    status: WorkflowStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    """Own workflows, newest first (admins see all), optionally by status."""
    query = (
        select(Workflow, Order)
        .join(Order, Workflow.order_id == Order.id)
        .order_by(Workflow.created_at.desc())
        .limit(limit)
    )

    if status is not None:
        query = query.where(Workflow.status == status.value)

    if current_user.role != UserRole.ADMIN.value:
        query = query.where(Order.user_id == current_user.id)

    return [
        WorkflowSummary(
            **WorkflowResponse.model_validate(workflow).model_dump(),
            product_id=order.product_id,
            quantity=order.quantity,
            order_status=order.status,
        )
        for workflow, order in db.execute(query).all()
    ]


@router.get(
    "/held-stock",
    response_model=list[WorkflowSummary],
)
def list_held_stock(
    db: DBSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    """Failed or in-review workflows that still hold reserved stock, the
    oldest first. These are candidates for a release_reservation."""
    query = (
        select(Workflow, Order)
        .join(Order, Workflow.order_id == Order.id)
        .join(InventoryReservation, InventoryReservation.order_id == Order.id)
        .where(
            InventoryReservation.status == "reserved",
            Workflow.status.in_(["failed", "needs_review"]),
        )
        .order_by(Workflow.updated_at.asc())
        .limit(limit)
    )

    if current_user.role != UserRole.ADMIN.value:
        query = query.where(Order.user_id == current_user.id)

    return [
        WorkflowSummary(
            **{
                **WorkflowResponse.model_validate(workflow).model_dump(),
                "reservation_status": "reserved",
            },
            product_id=order.product_id,
            quantity=order.quantity,
            order_status=order.status,
        )
        for workflow, order in db.execute(query).all()
    ]


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
    workflow = get_authorized_workflow(db, workflow_id, current_user)

    reservation_status = db.scalar(
        select(InventoryReservation.status).where(
            InventoryReservation.order_id == workflow.order_id
        )
    )
    has_invoice = (
        db.scalar(
            select(Invoice.id).where(Invoice.order_id == workflow.order_id)
        )
        is not None
    )

    return WorkflowResponse.model_validate(workflow).model_copy(
        update={
            "reservation_status": reservation_status,
            "has_invoice": has_invoice,
        }
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
        db, workflow_id, current_user
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


@router.post(
    "/{workflow_id}/reconcile",
    response_model=ReconcileResponse,
)
def reconcile_workflow(
    workflow_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    get_authorized_workflow(db, workflow_id, current_user)
    # Release the read transaction; the service manages its own.
    db.rollback()

    try:
        result = ReconciliationService.reconcile_reservation(
            db, workflow_id
        )
    except ReconciliationNotAllowed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReconciliationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return ReconcileResponse(
        workflow_id=result.workflow_id,
        operation_status=result.operation_status,
        reservation_found=result.reservation_found,
        next_step=result.next_step,
        workflow_status=result.workflow_status,
    )
