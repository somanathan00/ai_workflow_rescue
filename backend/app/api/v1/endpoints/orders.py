
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DBSession
from app.domain.enums import UserRole
from app.models import Order, Workflow
from app.repositories.order_repository import OrderRepository
from app.schemas.order import (
    OrderAcceptedResponse,
    OrderCreate,
    OrderListItem,
    OrderResponse,
)
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])



@router.post(
    "",
    response_model=OrderAcceptedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    payload: OrderCreate,
    db: DBSession,
    current_user: CurrentUser,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(min_length=1, max_length=128),
    ],
):
    order, created = OrderService.create_order(
        db=db,
        user_id=current_user.id,
        payload=payload,
        idempotency_key=idempotency_key,
    )

    workflow = OrderRepository.get_workflow(
        db, order.id
    )

    if workflow is None:
        raise HTTPException(
            status_code=500,
            detail="Order workflow missing",
        )

    if not created:
        response.status_code = status.HTTP_200_OK

    return OrderAcceptedResponse(
        order_id=order.id,
        workflow_id=workflow.id,
        status=order.status,
        message=(
            "Order accepted for processing"
            if created
            else "Existing order returned"
        ),
    )


@router.get(
    "",
    response_model=list[OrderListItem],
)
def list_orders(
    db: DBSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Own orders, newest first. Admins see every order."""
    query = (
        select(Order, Workflow.id, Workflow.status)
        .join(Workflow, Workflow.order_id == Order.id)
        .order_by(Order.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if current_user.role != UserRole.ADMIN.value:
        query = query.where(Order.user_id == current_user.id)

    return [
        OrderListItem(
            **OrderResponse.model_validate(order).model_dump(),
            workflow_id=workflow_id,
            workflow_status=status_,
        )
        for order, workflow_id, status_ in db.execute(query).all()
    ]


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
)
def get_order(
    order_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    order = OrderRepository.get_by_id(
        db=db,
        order_id=order_id,
        user_id=current_user.id,
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    return order
