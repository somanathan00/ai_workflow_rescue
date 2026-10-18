import random
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
    """
    ``Workflow.attempts`` counts executions claimed in the current
    processing cycle (incremented when a run starts, not when it fails).
    """

    # Total executions allowed: the first run plus two retries.
    MAX_ATTEMPTS = 3
    # Delay before execution N+1, indexed by completed attempts - 1.
    RETRY_DELAYS_SECONDS = (2, 4)

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

    @classmethod
    def retry_delay(
        cls,
        attempts: int,
        retryable: bool,
        jitter: bool = False,
    ) -> int | float | None:
        """Seconds to wait before the next execution, or None if the
        failure must not be retried automatically."""
        if not retryable or attempts >= cls.MAX_ATTEMPTS:
            return None

        index = min(attempts, len(cls.RETRY_DELAYS_SECONDS)) - 1
        delay = cls.RETRY_DELAYS_SECONDS[max(index, 0)]

        if jitter:
            return delay * random.uniform(0.75, 1.25)

        return delay
