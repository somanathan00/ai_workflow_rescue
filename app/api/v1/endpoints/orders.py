
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Response,
    status,
)

from app.api.dependencies import CurrentUser, DBSession
from app.repositories.order_repository import OrderRepository
from app.schemas.order import (
    OrderAcceptedResponse,
    OrderCreate,
    OrderResponse,
)
from app.services.order_service import OrderService

from app.infrastructure.messaging.publisher import WorkflowPublisher
router = APIRouter(prefix="/orders", tags=["Orders"])


from celery.exceptions import OperationalError


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

    if created:
        try:
            WorkflowPublisher.publish_order(workflow.id)
        except OperationalError:
            # The order is already committed.
            # Do not pretend the whole operation rolled back.
            raise HTTPException(
                status_code=503,
                detail=(
                    "Order saved, but background dispatch "
                    "is temporarily unavailable. Retry "
                    "with the same idempotency key."
                ),
            )

    else:
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
