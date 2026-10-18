from uuid import UUID

from sqlalchemy.orm import Session

from app.models import OutboxMessage


class OutboxPublisher:
    """Writes a message in the caller's transaction.

    It never talks to Redis and never commits: the calling service owns
    the transaction, so the message exists if and only if the state
    change that produced it commits.
    """

    @staticmethod
    def add(
        db: Session,
        event_type: str,
        aggregate_id: UUID,
        payload: dict,
    ) -> OutboxMessage:
        message = OutboxMessage(
            event_type=str(event_type),
            aggregate_id=aggregate_id,
            payload=payload,
        )
        db.add(message)
        return message
