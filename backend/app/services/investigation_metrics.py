"""How useful is the AI investigator? Computed from what people did with
its recommendations, not from the model's own confidence."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Investigation,
    InvestigationFeedback,
    Workflow,
    WorkflowRecoveryAction,
)

MAX_ROWS = 5000
STARTED = {"approved", "queued", "executing", "executed", "failed"}
BUCKETS = [
    ("below 0.6", 0.0, 0.6),
    ("0.6 - 0.8", 0.6, 0.8),
    ("0.8 - 0.9", 0.8, 0.9),
    ("0.9 and above", 0.9, 1.01),
]


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 3) if denominator else None


def _succeeded(action: WorkflowRecoveryAction, workflow_status: str) -> bool:
    """Did an executed recovery actually do its job?"""
    if action.status != "executed":
        return False

    if action.action_type == "release_reservation":
        return workflow_status == "compensated"

    if action.action_type == "mark_for_review":
        return True

    return workflow_status == "completed"


class InvestigationMetrics:

    @staticmethod
    def compute(db: Session, days: int = 30) -> dict:
        since = datetime.now(UTC) - timedelta(days=days)

        investigations = db.scalars(
            select(Investigation)
            .where(Investigation.created_at >= since)
            .order_by(Investigation.created_at.desc())
            .limit(MAX_ROWS)
        ).all()

        completed = [i for i in investigations if i.status == "completed"]
        workflow_ids = {i.workflow_id for i in investigations}

        recoveries = (
            db.scalars(
                select(WorkflowRecoveryAction)
                .where(WorkflowRecoveryAction.workflow_id.in_(workflow_ids))
                .order_by(WorkflowRecoveryAction.created_at.asc())
            ).all()
            if workflow_ids
            else []
        )
        workflow_status = (
            dict(
                db.execute(
                    select(Workflow.id, Workflow.status).where(
                        Workflow.id.in_(workflow_ids)
                    )
                ).all()
            )
            if workflow_ids
            else {}
        )
        feedback = (
            db.scalars(
                select(InvestigationFeedback).where(
                    InvestigationFeedback.investigation_id.in_(
                        [i.id for i in investigations]
                    )
                )
            ).all()
            if investigations
            else []
        )
        db.rollback()

        # ---- quality of the model's answers
        policies = [i.policy_result or {} for i in completed]
        downgraded = sum(1 for p in policies if p.get("downgraded"))
        unsupported = sum(1 for p in policies if p.get("unsupported_references"))
        violations = Counter(
            v[:90] for p in policies for v in p.get("violations", [])
        )
        final_actions = Counter(i.recommended_action for i in completed)
        model_actions = Counter(
            p.get("model_recommended_action") for p in policies
        )

        latencies = [i.latency_ms for i in completed if i.latency_ms]

        # ---- what happened to each actionable recommendation
        actionable = [
            i for i in completed
            if i.recommended_action not in (None, "no_action")
        ]
        funnel = Counter()
        bucket_stats = {
            name: Counter() for name, _, _ in BUCKETS
        }

        for inv in actionable:
            later = [
                a for a in recoveries
                if a.workflow_id == inv.workflow_id
                and a.created_at >= inv.created_at
            ]
            linked = [a for a in later if a.investigation_id == inv.id]
            same_type = [
                a for a in later if a.action_type == inv.recommended_action
            ]
            followed = (linked or same_type)[:1]
            bucket = next(
                name for name, lo, hi in BUCKETS
                if lo <= (inv.confidence or 0) < hi
            )
            bucket_stats[bucket]["actionable"] += 1

            if not later:
                funnel["no_recovery_requested"] += 1
                continue

            if not followed:
                funnel["overridden"] += 1
                continue

            action = followed[0]
            funnel["followed"] += 1
            bucket_stats[bucket]["followed"] += 1

            if action.status == "rejected":
                funnel["rejected"] += 1
            if action.status in STARTED:
                funnel["approved"] += 1
            if action.status == "executed":
                funnel["executed"] += 1
                bucket_stats[bucket]["executed"] += 1
            if _succeeded(action, workflow_status.get(inv.workflow_id, "")):
                funnel["succeeded"] += 1
                bucket_stats[bucket]["succeeded"] += 1

        # ---- explicit human verdicts
        helpful = sum(1 for f in feedback if f.rating == "helpful")
        not_helpful = sum(1 for f in feedback if f.rating == "not_helpful")

        return {
            "window_days": days,
            "investigations": {
                "total": len(investigations),
                "completed": len(completed),
                "failed": sum(1 for i in investigations if i.status == "failed"),
                "in_flight": sum(
                    1 for i in investigations if i.status in ("pending", "running")
                ),
            },
            "model": {
                "avg_confidence": (
                    round(mean(i.confidence for i in completed if i.confidence is not None), 3)
                    if any(i.confidence is not None for i in completed)
                    else None
                ),
                "avg_latency_ms": round(mean(latencies)) if latencies else None,
                "max_latency_ms": max(latencies) if latencies else None,
                "prompt_tokens": sum(i.prompt_tokens or 0 for i in completed),
                "completion_tokens": sum(i.completion_tokens or 0 for i in completed),
            },
            "guardrails": {
                "downgraded": downgraded,
                "downgrade_rate": _rate(downgraded, len(completed)),
                "unsupported_reference_rate": _rate(unsupported, len(completed)),
                "top_violations": [
                    {"reason": reason, "count": count}
                    for reason, count in violations.most_common(5)
                ],
            },
            "actions": {
                "final": dict(final_actions),
                "model_original": {
                    k: v for k, v in model_actions.items() if k
                },
            },
            "outcomes": {
                "actionable": len(actionable),
                "followed": funnel["followed"],
                "approved": funnel["approved"],
                "rejected": funnel["rejected"],
                "executed": funnel["executed"],
                "succeeded": funnel["succeeded"],
                "overridden": funnel["overridden"],
                "no_recovery_requested": funnel["no_recovery_requested"],
                "follow_rate": _rate(funnel["followed"], len(actionable)),
                "approval_rate": _rate(funnel["approved"], funnel["followed"]),
                "success_rate": _rate(funnel["succeeded"], funnel["executed"]),
            },
            "calibration": [
                {
                    "bucket": name,
                    "actionable": stats["actionable"],
                    "followed": stats["followed"],
                    "executed": stats["executed"],
                    "succeeded": stats["succeeded"],
                    "success_rate": _rate(stats["succeeded"], stats["executed"]),
                }
                for name, stats in bucket_stats.items()
            ],
            "feedback": {
                "helpful": helpful,
                "not_helpful": not_helpful,
                "helpful_rate": _rate(helpful, helpful + not_helpful),
                "coverage": _rate(helpful + not_helpful, len(completed)),
            },
        }
