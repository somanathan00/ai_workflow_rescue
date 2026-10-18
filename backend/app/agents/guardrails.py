from dataclasses import dataclass, field

from app.agents.schemas import InvestigationResult
from app.domain.enums import RecommendedAction, RecoveryActionType
from app.domain.policies.recovery_policy import RecoveryPolicy

MIN_CONFIDENCE = 0.6


@dataclass
class GuardrailOutcome:
    action: RecommendedAction
    requires_approval: bool
    original_action: RecommendedAction
    violations: list[str] = field(default_factory=list)
    unsupported_references: list[str] = field(default_factory=list)
    supported_evidence: list[dict] = field(default_factory=list)

    @property
    def downgraded(self) -> bool:
        return self.action != self.original_action

    def as_dict(self) -> dict:
        return {
            "model_recommended_action": self.original_action.value,
            "final_action": self.action.value,
            "downgraded": self.downgraded,
            "violations": self.violations,
            "unsupported_references": self.unsupported_references,
        }


def collect_references(evidence: dict) -> set[str]:
    """Every `ref` the tools produced; the only things the model may cite."""
    refs: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            ref = node.get("ref")
            if isinstance(ref, str):
                refs.add(ref)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(evidence)
    return refs


def _policy_allows(
    action: RecommendedAction,
    workflow: dict,
    reservation_status: str | None = None,
) -> bool:
    if action == RecommendedAction.NO_ACTION:
        return True

    try:
        RecoveryPolicy.validate(
            workflow["status"],
            workflow.get("last_error_code"),
            RecoveryActionType(action.value),
            workflow.get("current_step"),
            reservation_status,
        )
    except ValueError:
        return False

    return True


def apply_guardrails(
    result: InvestigationResult,
    evidence: dict,
) -> GuardrailOutcome:
    """Deterministic checks on a model recommendation. The result can
    only stay the same or become safer; it is never an authorization."""
    workflow = evidence["workflow"]
    reservation = evidence.get("reservation", {})
    operations = evidence.get("operations", [])
    uncertain = any(op["status"] == "uncertain" for op in operations)
    reservation_confirmed = bool(
        reservation.get("exists") and reservation.get("matches_order")
    )
    reservation_status = (
        reservation.get("status") if reservation.get("exists") else None
    )

    original = result.recommended_action
    action = original
    violations: list[str] = []

    valid_refs = collect_references(evidence)
    supported = [
        item.model_dump()
        for item in result.evidence
        if item.reference in valid_refs
    ]
    unsupported = [
        item.reference
        for item in result.evidence
        if item.reference not in valid_refs
    ]

    def downgrade(reason: str) -> None:
        nonlocal action
        violations.append(reason)
        action = RecommendedAction.MARK_FOR_REVIEW

    if workflow["status"] in ("completed", "compensated"):
        if action != RecommendedAction.NO_ACTION:
            violations.append(
                f"workflow is {workflow['status']}; nothing to recover"
            )
        action = RecommendedAction.NO_ACTION
    else:
        if unsupported:
            downgrade("cited evidence that was not supplied")
        elif not supported and action != RecommendedAction.NO_ACTION:
            downgrade("recommendation cites no supported evidence")

        if result.confidence < MIN_CONFIDENCE:
            downgrade(
                f"confidence {result.confidence:.2f} is below "
                f"{MIN_CONFIDENCE}"
            )

        # Retrying the reserve step over an existing/uncertain reservation
        # could reserve twice. Retrying a later step (e.g. the invoice)
        # does not touch the reservation, so it is not blocked here.
        if (
            action == RecommendedAction.RETRY_WORKFLOW
            and workflow.get("current_step") == "reserve_inventory"
            and (reservation.get("exists") or uncertain)
        ):
            downgrade(
                "retry would repeat a side effect that may already "
                "have happened"
            )
            if uncertain and reservation_confirmed:
                action = RecommendedAction.RECONCILE_AND_RESUME

        if action == RecommendedAction.RECONCILE_AND_RESUME and not (
            uncertain and reservation_confirmed
        ):
            downgrade(
                "reconciliation needs an uncertain operation and a "
                "matching reservation; absence is not proof"
            )

        if (
            action == RecommendedAction.RELEASE_RESERVATION
            and not reservation_confirmed
        ):
            downgrade(
                "release needs a reservation that matches this order; "
                "releasing a missing or conflicting one could free stock "
                "that belongs to someone else"
            )

        if not _policy_allows(action, workflow, reservation_status):
            violations.append(
                f"{action.value} is not allowed by recovery policy for "
                f"this workflow state"
            )
            action = RecommendedAction.MARK_FOR_REVIEW

        if not _policy_allows(action, workflow, reservation_status):
            action = RecommendedAction.NO_ACTION

    return GuardrailOutcome(
        action=action,
        requires_approval=action != RecommendedAction.NO_ACTION,
        original_action=original,
        violations=violations,
        unsupported_references=unsupported,
        supported_evidence=supported,
    )
