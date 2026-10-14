
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.enums import WorkflowStatus, WorkflowStep


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    status: WorkflowStatus
    current_step: WorkflowStep | None
    attempts: int
    last_error_code: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime


class WorkflowEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    step: WorkflowStep | None
    event_type: str
    details: dict[str, Any]
    created_at: datetime
