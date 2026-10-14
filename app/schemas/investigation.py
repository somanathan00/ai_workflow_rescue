
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    InvestigationStatus,
    RecoveryAction,
    RecoveryStatus,
)


class InvestigationEvidence(BaseModel):
    source: str
    reference: str
    observation: str


class AIInvestigationResult(BaseModel):
    root_cause: str
    recommended_action: RecoveryAction
    reasoning: str
    evidence: list[InvestigationEvidence] = Field(
        default_factory=list,
    )
    requires_approval: bool = True


class InvestigationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    status: InvestigationStatus
    root_cause: str | None
    recommended_action: RecoveryAction | None
    reasoning: str | None
    requires_approval: bool
    created_at: datetime


class RecoveryRequest(BaseModel):
    action: RecoveryAction
    reason: str = Field(min_length=3, max_length=1000)


class RecoveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    action: RecoveryAction
    status: RecoveryStatus
    created_at: datetime
