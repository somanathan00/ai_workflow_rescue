import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.domain.enums import OutboxEventType
from app.infrastructure.database.session import SessionLocal
from app.models import OutboxMessage
from app.workers.investigation_tasks import run_investigation
from app.workers.order_tasks import process_order
from app.workers.recovery_tasks import execute_recovery

logger = logging.getLogger(__name__)

BATCH_SIZE = 20
CLAIM_DURATION = timedelta(seconds=30)
MAX_BACKOFF_SECONDS = 60


def _publish(event_type: str, payload: dict) -> None:
    """Fixed allowlist of event types. Never resolves a task name from
    message contents. retry=False keeps each publish bounded when the
    broker is down; the dispatcher's own backoff handles retrying."""
    if event_type in (
        OutboxEventType.WORKFLOW_START,
        OutboxEventType.WORKFLOW_RESUME,
    ):
        process_order.apply_async(
            args=[payload["workflow_id"]],
            queue="workflow",
            retry=False,
        )
    elif event_type == OutboxEventType.RECOVERY_EXECUTE:
        execute_recovery.apply_async(
            args=[payload["recovery_action_id"]],
            queue="workflow",
            retry=False,
        )
    elif event_type == OutboxEventType.INVESTIGATION_START:
        run_investigation.apply_async(
            args=[payload["investigation_id"]],
            queue="investigations",
            retry=False,
        )
    else:
        raise ValueError(f"Unsupported event type: {event_type}")


class OutboxDispatcher:

    @staticmethod
    def _claim_batch() -> list[tuple[uuid.UUID, str, dict, str]]:
        """Claim due messages in a short transaction. SKIP LOCKED lets
        several dispatchers share the table; an unsettled claim simply
        expires and the message is picked up again."""
        token = uuid.uuid4().hex
        now = datetime.now(UTC)

        with SessionLocal.begin() as db:
            messages = db.scalars(
                select(OutboxMessage)
                .where(
                    OutboxMessage.status == "pending",
                    OutboxMessage.next_attempt_at <= now,
                    (OutboxMessage.claimed_until.is_(None))
                    | (OutboxMessage.claimed_until < now),
                )
                .order_by(
                    OutboxMessage.next_attempt_at,
                    OutboxMessage.created_at,
                )
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            ).all()

            for message in messages:
                message.claim_token = token
                message.claimed_until = now + CLAIM_DURATION

            return [
                (m.id, m.event_type, dict(m.payload), token)
                for m in messages
            ]

    @staticmethod
    def _mark_published(message_id: uuid.UUID, token: str) -> None:
        with SessionLocal.begin() as db:
            db.execute(
                update(OutboxMessage)
                .where(
                    OutboxMessage.id == message_id,
                    OutboxMessage.claim_token == token,
                )
                .values(
                    status="published",
                    published_at=datetime.now(UTC),
                    claim_token=None,
                    claimed_until=None,
                    last_error=None,
                )
            )

    @staticmethod
    def _mark_failed(
        message_id: uuid.UUID,
        token: str,
        error: Exception,
        poison: bool = False,
    ) -> None:
        with SessionLocal.begin() as db:
            message = db.scalar(
                select(OutboxMessage)
                .where(
                    OutboxMessage.id == message_id,
                    OutboxMessage.claim_token == token,
                )
                .with_for_update()
            )

            if message is None:
                return

            message.attempts += 1
            message.last_error = str(error)[:500]
            message.claim_token = None
            message.claimed_until = None

            if poison:
                message.status = "dead"
                return

            delay = min(2 ** message.attempts, MAX_BACKOFF_SECONDS)
            message.next_attempt_at = (
                datetime.now(UTC) + timedelta(seconds=delay)
            )

    @staticmethod
    def _release(message_id: uuid.UUID, token: str) -> None:
        """Give a claimed message back without counting an attempt."""
        with SessionLocal.begin() as db:
            db.execute(
                update(OutboxMessage)
                .where(
                    OutboxMessage.id == message_id,
                    OutboxMessage.claim_token == token,
                )
                .values(claim_token=None, claimed_until=None)
            )

    @classmethod
    def dispatch_once(cls) -> int:
        """Publish one batch; returns how many messages were claimed.
        No database transaction is open while publishing."""
        batch = cls._claim_batch()
        broker_down = False

        for message_id, event_type, payload, token in batch:
            if broker_down:
                cls._release(message_id, token)
                continue

            try:
                _publish(event_type, payload)
            except ValueError as exc:
                logger.error(
                    "outbox_message_dead",
                    extra={"outbox_id": str(message_id)},
                )
                cls._mark_failed(message_id, token, exc, poison=True)
            except Exception as exc:
                logger.warning(
                    "outbox_publish_failed",
                    exc_info=True,
                    extra={"outbox_id": str(message_id)},
                )
                cls._mark_failed(message_id, token, exc)
                # Broker is likely down: stop hammering it this round.
                broker_down = True
            else:
                cls._mark_published(message_id, token)

        return len(batch)
