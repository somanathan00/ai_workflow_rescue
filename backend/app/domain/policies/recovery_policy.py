from app.domain.enums import RecoveryActionStatus, RecoveryActionType

S = RecoveryActionStatus

# Allowed state transitions. failed is terminal: recovering again needs a
# new recovery action after reassessment.
TRANSITIONS: dict[RecoveryActionStatus, frozenset[RecoveryActionStatus]] = {
    S.REQUESTED: frozenset({S.APPROVED, S.REJECTED}),
    S.APPROVED: frozenset({S.QUEUED}),
    S.QUEUED: frozenset({S.EXECUTING}),
    S.EXECUTING: frozenset({S.EXECUTED, S.FAILED}),
    S.REJECTED: frozenset(),
    S.EXECUTED: frozenset(),
    S.FAILED: frozenset(),
}


class RecoveryPolicy:
    """Deterministic rules deciding what recovery is allowed.

    An AI recommendation is advisory only; every action is validated here
    against live workflow state, both when it is requested/approved and
    again when it executes.
    """

    @staticmethod
    def can_transition(
        current: RecoveryActionStatus,
        new: RecoveryActionStatus,
    ) -> bool:
        return new in TRANSITIONS[current]

    @staticmethod
    def validate(
        workflow_status: str,
        error_code: str | None,
        action_type: RecoveryActionType,
        current_step: str | None = None,
        reservation_status: str | None = None,
    ) -> None:
        if workflow_status == "completed":
            raise ValueError("Completed workflows cannot be recovered")

        if workflow_status == "compensated":
            raise ValueError(
                "This workflow was already compensated; place a new order"
            )

        if action_type == RecoveryActionType.RETRY_WORKFLOW:
            # Only a failure known to be safe to repeat. Never a way
            # around an unresolved uncertain outcome.
            if (
                workflow_status != "failed"
                or error_code != "TRANSIENT_ERROR"
            ):
                raise ValueError("Retry is not allowed for this failure")

        elif action_type == RecoveryActionType.RECONCILE_AND_RESUME:
            if (
                workflow_status != "needs_review"
                or error_code != "UNCERTAIN_OUTCOME"
            ):
                raise ValueError(
                    "Reconciliation requires an uncertain outcome"
                )

            if current_step not in (None, "reserve_inventory"):
                raise ValueError(
                    "Reconciliation applies to the reserve_inventory step"
                )

        elif action_type == RecoveryActionType.MARK_FOR_REVIEW:
            if workflow_status not in ("failed", "needs_review"):
                raise ValueError("Workflow is not eligible for review")

        elif action_type == RecoveryActionType.RELEASE_RESERVATION:
            # Compensation. "released" is accepted so a run that crashed
            # after the provider released the stock can finish cleanly.
            if workflow_status not in ("failed", "needs_review"):
                raise ValueError(
                    "Release applies only to failed or in-review workflows"
                )

            if reservation_status not in ("reserved", "released"):
                raise ValueError("There is no reservation to release")

        else:
            raise ValueError("Unsupported recovery action")
