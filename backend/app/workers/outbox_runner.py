import logging
import signal
import threading
from pathlib import Path

from app.core.logging import configure_logging
from app.infrastructure.messaging.outbox_dispatcher import (
    BATCH_SIZE,
    OutboxDispatcher,
)

logger = logging.getLogger("outbox_runner")

POLL_INTERVAL_SECONDS = 1.0
# Touched every cycle; the container healthcheck reads its age.
HEARTBEAT_FILE = Path("/tmp/outbox_heartbeat")

stop = threading.Event()


def main() -> None:
    configure_logging()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    logger.info("outbox dispatcher started")

    while not stop.is_set():
        HEARTBEAT_FILE.touch()

        try:
            claimed = OutboxDispatcher.dispatch_once()
        except Exception:
            # Database unavailable, etc. Keep the loop alive.
            logger.exception("outbox dispatch cycle failed")
            claimed = 0

        # A full batch means more work is probably waiting.
        if claimed < BATCH_SIZE:
            stop.wait(POLL_INTERVAL_SECONDS)

    logger.info("outbox dispatcher stopped")


if __name__ == "__main__":
    main()
