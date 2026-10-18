from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.agents.schemas import EvidenceItem
from app.domain.enums import FeedbackRating, InvestigationStatus, RecommendedAction


class FeedbackRequest(BaseModel):
    rating: FeedbackRating
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rating: FeedbackRating
    comment: str | None
    updated_at: datetime


class InvestigationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    status: InvestigationStatus
    root_cause: str | None
    recommended_action: RecommendedAction | None
    reasoning: str | None
    evidence: list[EvidenceItem]
    confidence: float | None
    requires_approval: bool
    policy_result: dict[str, Any] | None
    error_message: str | None
    model_name: str | None
    prompt_version: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int | None
    created_at: datetime
    updated_at: datetime
    # The requesting user's own verdict, if they gave one.
    my_feedback: FeedbackResponse | None = None
