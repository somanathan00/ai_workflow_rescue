from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import RecoveryActionStatus, RecoveryActionType


class RecoveryRequest(BaseModel):
    action_type: RecoveryActionType
    reason: str = Field(min_length=10, max_length=1000)
    # Optional: the investigation this recovery follows. Its
    # recommendation must match the requested action.
    investigation_id: UUID | None = None


class RecoveryRejection(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class RecoveryActionResponse(BaseModel):
    # status, approved_by etc. are set by the backend, never the client.
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    action_type: RecoveryActionType
    status: RecoveryActionStatus
    reason: str
    investigation_id: UUID | None = None
    requested_by: UUID
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    rejected_by: UUID | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    executed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
