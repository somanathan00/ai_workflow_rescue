from fastapi import APIRouter, Response, status
from redis import Redis
from sqlalchemy import func, select, text

from app.core.config import settings
from app.infrastructure.database.session import SessionLocal
from app.models import (
    InventoryReservation,
    Investigation,
    InvestigationFeedback,
    Order,
    OutboxMessage,
    Workflow,
    WorkflowRecoveryAction,
)

router = APIRouter(tags=["Health"])


@router.get("/health/live")
def liveness():
    return {"status": "alive"}


@router.get("/health/ready")
def readiness(response: Response):
    """Dependencies the API needs to serve requests. Redis is reported but
    not required: orders are accepted through the outbox while it is down."""
    checks: dict[str, str] = {}

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unavailable"

    try:
        Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1).ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    ready = checks["postgres"] == "ok"

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ready" if ready else "not_ready", "checks": checks}


def _gauge(lines: list[str], name: str, help_text: str, rows, label: str):
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} gauge")
    for key, value in rows:
        lines.append(f'{name}{{{label}="{key}"}} {value}')


@router.get("/metrics")
def metrics() -> Response:
    """Prometheus text format, derived from PostgreSQL state. Exposes
    aggregate counts only; keep it on the internal network."""
    lines: list[str] = []

    with SessionLocal() as db:
        _gauge(
            lines, "workflows_total", "Workflows by status",
            db.execute(
                select(Workflow.status, func.count()).group_by(Workflow.status)
            ).all(),
            "status",
        )
        _gauge(
            lines, "outbox_messages", "Outbox messages by status",
            db.execute(
                select(OutboxMessage.status, func.count()).group_by(
                    OutboxMessage.status
                )
            ).all(),
            "status",
        )
        _gauge(
            lines, "recovery_actions_total", "Recovery actions by status",
            db.execute(
                select(
                    WorkflowRecoveryAction.status, func.count()
                ).group_by(WorkflowRecoveryAction.status)
            ).all(),
            "status",
        )
        _gauge(
            lines, "investigations_total", "Investigations by status",
            db.execute(
                select(Investigation.status, func.count()).group_by(
                    Investigation.status
                )
            ).all(),
            "status",
        )

        held = db.execute(
            select(
                func.count(),
                func.coalesce(
                    func.extract("epoch", func.now() - func.min(Workflow.updated_at)),
                    0,
                ),
            )
            .select_from(Workflow)
            .join(Order, Order.id == Workflow.order_id)
            .join(InventoryReservation, InventoryReservation.order_id == Order.id)
            .where(
                InventoryReservation.status == "reserved",
                Workflow.status.in_(["failed", "needs_review"]),
            )
        ).one()
        downgraded = db.scalar(
            select(func.count()).where(
                Investigation.policy_result["downgraded"].astext == "true"
            )
        )
        _gauge(
            lines, "investigation_feedback_total", "AI investigation feedback",
            db.execute(
                select(InvestigationFeedback.rating, func.count()).group_by(
                    InvestigationFeedback.rating
                )
            ).all(),
            "rating",
        )
        oldest = db.scalar(
            select(
                func.coalesce(
                    func.extract("epoch", func.now() - func.min(OutboxMessage.created_at)),
                    0,
                )
            ).where(OutboxMessage.status == "pending")
        )
        retries = db.scalar(
            select(func.coalesce(func.sum(Workflow.attempts), 0))
        )
        tokens = db.execute(
            select(
                func.coalesce(func.sum(Investigation.prompt_tokens), 0),
                func.coalesce(func.sum(Investigation.completion_tokens), 0),
                func.coalesce(func.avg(Investigation.latency_ms), 0),
            )
        ).one()

    lines += [
        "# HELP held_reservations Reservations still held by failed or in-review workflows",
        "# TYPE held_reservations gauge",
        f"held_reservations {held[0]}",
        "# HELP held_reservations_oldest_age_seconds Age of the longest-held stock",
        "# TYPE held_reservations_oldest_age_seconds gauge",
        f"held_reservations_oldest_age_seconds {float(held[1] or 0):.1f}",
        "# HELP investigation_guardrail_downgrades_total Model answers changed by guardrails",
        "# TYPE investigation_guardrail_downgrades_total gauge",
        f"investigation_guardrail_downgrades_total {downgraded or 0}",
        "# HELP outbox_oldest_pending_age_seconds Age of the oldest undelivered message",
        "# TYPE outbox_oldest_pending_age_seconds gauge",
        f"outbox_oldest_pending_age_seconds {float(oldest or 0):.1f}",
        "# HELP workflow_execution_attempts_total Executions claimed across all workflows",
        "# TYPE workflow_execution_attempts_total gauge",
        f"workflow_execution_attempts_total {retries}",
        "# HELP gemini_prompt_tokens_total Prompt tokens used by investigations",
        "# TYPE gemini_prompt_tokens_total gauge",
        f"gemini_prompt_tokens_total {tokens[0]}",
        "# HELP gemini_completion_tokens_total Completion tokens used by investigations",
        "# TYPE gemini_completion_tokens_total gauge",
        f"gemini_completion_tokens_total {tokens[1]}",
        "# HELP gemini_latency_ms_avg Average Gemini latency",
        "# TYPE gemini_latency_ms_avg gauge",
        f"gemini_latency_ms_avg {float(tokens[2]):.1f}",
    ]

    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
