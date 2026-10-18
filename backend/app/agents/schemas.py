from pydantic import BaseModel, Field

from app.domain.enums import RecommendedAction


class EvidenceItem(BaseModel):
    source: str = Field(description="Tool the fact came from, e.g. reservation_lookup")
    reference: str = Field(
        description="A `ref` value copied exactly from the supplied evidence"
    )
    observation: str = Field(description="What that evidence shows")


class InvestigationResult(BaseModel):
    """Contract for the model's output. Advisory only: it is validated by
    guardrails and never authorizes anything by itself."""

    root_cause: str
    recommended_action: RecommendedAction
    reasoning: str
    evidence: list[EvidenceItem]
    # Model-reported estimate, not a calibrated probability.
    confidence: float = Field(ge=0, le=1)
    requires_approval: bool
