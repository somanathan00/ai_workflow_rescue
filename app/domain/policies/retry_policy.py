
from dataclasses import dataclass

from app.domain.exceptions import (
    PermanentWorkflowError,
    TransientWorkflowError,
    UncertainOutcomeError,
)


@dataclass(frozen=True)
class FailureDecision:
    error_code: str
    retryable: bool
    requires_review: bool


class RetryPolicy:

    MAX_ATTEMPTS = 3

    @staticmethod
    def classify(
        error: Exception,
    ) -> FailureDecision:

        if isinstance(error, TransientWorkflowError):
            return FailureDecision(
                error_code="TRANSIENT_ERROR",
                retryable=True,
                requires_review=False,
            )

        if isinstance(error, UncertainOutcomeError):
            return FailureDecision(
                error_code="UNCERTAIN_OUTCOME",
                retryable=False,
                requires_review=True,
            )

        if isinstance(error, PermanentWorkflowError):
            return FailureDecision(
                error_code="PERMANENT_ERROR",
                retryable=False,
                requires_review=False,
            )

        return FailureDecision(
            error_code="UNEXPECTED_ERROR",
            retryable=False,
            requires_review=True,
        )
