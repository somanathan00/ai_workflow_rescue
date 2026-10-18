from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, status

from app.api.dependencies import AdminUser, CurrentUser, DBSession
from app.domain.enums import RecoveryActionStatus
from app.schemas.recovery import (
    RecoveryActionResponse,
    RecoveryRejection,
    RecoveryRequest,
)
from app.services.recovery_service import RecoveryService

router = APIRouter(
    prefix="/workflows/{workflow_id}/recovery-actions",
    tags=["Recovery"],
)


@router.post(
    "",
    response_model=RecoveryActionResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_recovery(
    workflow_id: UUID,
    payload: RecoveryRequest,
    db: DBSession,
    current_user: CurrentUser,
    idempotency_key: Annotated[
        str | None,
        Header(min_length=1, max_length=128),
    ] = None,
):
    return RecoveryService.request(
        db,
        workflow_id,
        current_user,
        payload.action_type,
        payload.reason,
        idempotency_key,
        payload.investigation_id,
    )


@router.get(
    "",
    response_model=list[RecoveryActionResponse],
)
def list_recovery_actions(
    workflow_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    return RecoveryService.list_actions(db, workflow_id, current_user)


@router.post(
    "/{action_id}/approve",
    response_model=RecoveryActionResponse,
)
def approve_recovery(
    workflow_id: UUID,
    action_id: UUID,
    db: DBSession,
    admin: AdminUser,
):
    return RecoveryService.approve(db, workflow_id, action_id, admin)


@router.post(
    "/{action_id}/reject",
    response_model=RecoveryActionResponse,
)
def reject_recovery(
    workflow_id: UUID,
    action_id: UUID,
    payload: RecoveryRejection,
    db: DBSession,
    admin: AdminUser,
):
    return RecoveryService.reject(
        db, workflow_id, action_id, admin, payload.reason
    )


@router.post(
    "/{action_id}/execute",
    response_model=RecoveryActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def execute_recovery(
    workflow_id: UUID,
    action_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    # Only queues the work (action + outbox message commit together);
    # the Celery worker performs it.
    return RecoveryService.queue_execution(
        db, workflow_id, action_id, current_user
    )


queue_router = APIRouter(
    prefix="/recovery-actions",
    tags=["Recovery"],
)


@queue_router.get(
    "",
    response_model=list[RecoveryActionResponse],
)
def list_all_recovery_actions(
    db: DBSession,
    current_user: CurrentUser,
    status: RecoveryActionStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    """Cross-workflow queue, e.g. `?status=requested` for the approval
    inbox. Admins see everything; operators only their own workflows."""
    return RecoveryService.list_all(
        db,
        current_user,
        status.value if status else None,
        limit,
    )
