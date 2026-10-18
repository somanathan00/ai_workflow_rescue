import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.investigator import (
    Analyzer,
    WorkflowMissing,
    run_investigation_graph,
)
from app.domain.enums import OutboxEventType, UserRole
from app.infrastructure.messaging.outbox_publisher import OutboxPublisher
from app.models import (
    Investigation,
    InvestigationFeedback,
    Order,
    User,
    Workflow,
    WorkflowEvent,
)

logger = logging.getLogger(__name__)

# A `running` investigation older than this is presumed orphaned.
STALE_RUNNING = timedelta(minutes=10)
ACTIVE = ("pending", "running")


def _now() -> datetime:
    return datetime.now(UTC)


class InvestigationService:

    # ------------------------------------------------------------ access
    @staticmethod
    def _authorized_workflow(
        db: Session, workflow_id: UUID, user: User
    ) -> Workflow:
        workflow = db.get(Workflow, workflow_id)
        order = db.get(Order, workflow.order_id) if workflow else None

        if order is None or not (
            order.user_id == user.id
            or user.role == UserRole.ADMIN.value
        ):
            db.rollback()
            raise HTTPException(404, "Workflow not found")

        return workflow

    # ------------------------------------------------------------- API
    @staticmethod
    def start(
        db: Session, workflow_id: UUID, user: User
    ) -> Investigation:
        """Create a pending investigation and queue it via the outbox.
        Idempotent while one is already in flight."""
        workflow = InvestigationService._authorized_workflow(
            db, workflow_id, user
        )

        active = db.scalar(
            select(Investigation).where(
                Investigation.workflow_id == workflow_id,
                Investigation.status.in_(ACTIVE),
            )
        )

        if active is not None:
            db.rollback()
            return active

        investigation = Investigation(
            workflow_id=workflow.id,
            status="pending",
            evidence=[],
            requires_approval=True,
        )
        db.add(investigation)
        db.flush()

        OutboxPublisher.add(
            db,
            OutboxEventType.INVESTIGATION_START,
            investigation.id,
            {"investigation_id": str(investigation.id)},
        )
        db.add(
            WorkflowEvent(
                workflow_id=workflow.id,
                step=workflow.current_step,
                event_type="investigation_requested",
                details={
                    "investigation_id": str(investigation.id),
                    "requested_by": str(user.id),
                },
            )
        )

        try:
            db.commit()
        except IntegrityError:
            # Concurrent request created one first (partial unique index).
            db.rollback()
            active = db.scalar(
                select(Investigation).where(
                    Investigation.workflow_id == workflow_id,
                    Investigation.status.in_(ACTIVE),
                )
            )
            if active is None:
                raise
            return active

        db.refresh(investigation)
        return investigation

    @staticmethod
    def _attach_feedback(
        db: Session, investigations: list[Investigation], user: User
    ) -> None:
        """Expose the requesting user's own verdict on each investigation."""
        ids = [i.id for i in investigations]
        mine = {}

        if ids:
            mine = {
                f.investigation_id: f
                for f in db.scalars(
                    select(InvestigationFeedback).where(
                        InvestigationFeedback.investigation_id.in_(ids),
                        InvestigationFeedback.user_id == user.id,
                    )
                )
            }

        for investigation in investigations:
            investigation.my_feedback = mine.get(investigation.id)

    @staticmethod
    def set_feedback(
        db: Session,
        investigation_id: UUID,
        user: User,
        rating: str,
        comment: str | None,
    ) -> InvestigationFeedback:
        """Record whether this investigation helped. One verdict per
        person; sending it again replaces the previous one."""
        investigation = InvestigationService.get(db, investigation_id, user)

        if investigation.status not in ("completed", "failed"):
            raise HTTPException(409, "Wait until the investigation finishes")

        feedback = db.scalar(
            select(InvestigationFeedback).where(
                InvestigationFeedback.investigation_id == investigation_id,
                InvestigationFeedback.user_id == user.id,
            )
        )

        if feedback is None:
            feedback = InvestigationFeedback(
                investigation_id=investigation_id,
                user_id=user.id,
                rating=rating,
                comment=comment,
            )
            db.add(feedback)
        else:
            feedback.rating = rating
            feedback.comment = comment
            feedback.updated_at = _now()

        db.commit()
        db.refresh(feedback)
        return feedback

    @staticmethod
    def list_for_workflow(
        db: Session, workflow_id: UUID, user: User
    ) -> list[Investigation]:
        InvestigationService._authorized_workflow(db, workflow_id, user)
        rows = db.scalars(
            select(Investigation)
            .where(Investigation.workflow_id == workflow_id)
            .order_by(Investigation.created_at.desc())
            .limit(50)
        ).all()
        rows = list(rows)
        InvestigationService._attach_feedback(db, rows, user)
        db.rollback()
        return rows

    @staticmethod
    def get(
        db: Session, investigation_id: UUID, user: User
    ) -> Investigation:
        investigation = db.get(Investigation, investigation_id)

        if investigation is None:
            raise HTTPException(404, "Investigation not found")

        InvestigationService._authorized_workflow(
            db, investigation.workflow_id, user
        )
        InvestigationService._attach_feedback(db, [investigation], user)
        db.rollback()
        return investigation

    # ----------------------------------------------------------- worker
    @staticmethod
    def run(
        db: Session,
        investigation_id: UUID,
        analyzer: Analyzer | None = None,
    ) -> None:
        """Worker entry point; safe under duplicate delivery."""
        investigation = db.scalar(
            select(Investigation)
            .where(Investigation.id == investigation_id)
            .with_for_update()
        )

        if investigation is None:
            db.rollback()
            return

        stale = (
            investigation.status == "running"
            and investigation.updated_at < _now() - STALE_RUNNING
        )

        if investigation.status != "pending" and not stale:
            db.rollback()
            return

        investigation.status = "running"
        investigation.updated_at = _now()
        workflow_id = investigation.workflow_id
        db.commit()

        try:
            state = run_investigation_graph(workflow_id, analyzer)
        except WorkflowMissing:
            InvestigationService._fail(
                db, investigation_id, "Workflow not found"
            )
            return
        except Exception as exc:
            logger.exception(
                "investigation_failed",
                extra={"investigation_id": str(investigation_id)},
            )
            InvestigationService._fail(
                db, investigation_id, f"{type(exc).__name__}: {exc}"
            )
            return

        if "analysis_error" in state:
            InvestigationService._fail(
                db, investigation_id, state["analysis_error"]
            )
            return

        InvestigationService._complete(db, investigation_id, state)

    @staticmethod
    def _fail(db: Session, investigation_id: UUID, message: str) -> None:
        db.rollback()
        investigation = db.get(Investigation, investigation_id)
        investigation.status = "failed"
        investigation.error_message = message[:1000]
        InvestigationService._event(
            db, investigation, "investigation_failed",
            {"error": message[:300]},
        )
        db.commit()

    @staticmethod
    def _complete(
        db: Session, investigation_id: UUID, state: dict
    ) -> None:
        result = state["result"]
        outcome = state["outcome"]
        usage = state.get("usage")

        investigation = db.get(Investigation, investigation_id)
        investigation.status = "completed"
        investigation.root_cause = result.root_cause
        investigation.reasoning = result.reasoning
        # Only evidence the tools actually produced is kept.
        investigation.evidence = outcome.supported_evidence
        investigation.recommended_action = outcome.action.value
        investigation.requires_approval = outcome.requires_approval
        investigation.confidence = result.confidence
        investigation.policy_result = outcome.as_dict()
        investigation.prompt_version = state.get("prompt_version")

        if usage is not None:
            investigation.model_name = usage.model
            investigation.prompt_tokens = usage.prompt_tokens
            investigation.completion_tokens = usage.completion_tokens
            investigation.latency_ms = usage.latency_ms
            logger.info(
                "gemini_usage",
                extra={
                    "investigation_id": str(investigation_id),
                    "model": usage.model,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "latency_ms": usage.latency_ms,
                },
            )

        InvestigationService._event(
            db, investigation, "investigation_completed",
            {
                "recommended_action": outcome.action.value,
                "downgraded": outcome.downgraded,
            },
        )
        db.commit()

    @staticmethod
    def _event(
        db: Session,
        investigation: Investigation,
        event_type: str,
        details: dict,
    ) -> None:
        workflow = db.get(Workflow, investigation.workflow_id)

        if workflow is not None:
            db.add(
                WorkflowEvent(
                    workflow_id=workflow.id,
                    step=workflow.current_step,
                    event_type=event_type,
                    details={
                        "investigation_id": str(investigation.id),
                        **details,
                    },
                )
            )
