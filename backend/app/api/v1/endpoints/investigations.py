from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.dependencies import AdminUser, CurrentUser, DBSession
from app.schemas.investigation import (
    FeedbackRequest,
    FeedbackResponse,
    InvestigationResponse,
)
from app.services.investigation_metrics import InvestigationMetrics
from app.services.investigation_service import InvestigationService

router = APIRouter(tags=["Investigations"])


@router.post(
    "/workflows/{workflow_id}/investigate",
    response_model=InvestigationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_investigation(
    workflow_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    # Creates a pending record and queues it through the outbox.
    return InvestigationService.start(db, workflow_id, current_user)


@router.get(
    "/workflows/{workflow_id}/investigations",
    response_model=list[InvestigationResponse],
)
def list_investigations(
    workflow_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    return InvestigationService.list_for_workflow(
        db, workflow_id, current_user
    )


@router.get(
    "/investigations/{investigation_id}",
    response_model=InvestigationResponse,
)
def get_investigation(
    investigation_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    return InvestigationService.get(db, investigation_id, current_user)


@router.put(
    "/investigations/{investigation_id}/feedback",
    response_model=FeedbackResponse,
)
def give_feedback(
    investigation_id: UUID,
    payload: FeedbackRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Say whether an investigation helped. Replaces your earlier verdict."""
    return InvestigationService.set_feedback(
        db,
        investigation_id,
        current_user,
        payload.rating.value,
        payload.comment,
    )


@router.get("/investigation-metrics")
def investigation_metrics(
    db: DBSession,
    admin: AdminUser,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
):
    """How useful the AI investigator has been (admins only)."""
    return InvestigationMetrics.compute(db, days)
