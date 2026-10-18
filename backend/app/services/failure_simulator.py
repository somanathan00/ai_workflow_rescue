
from app.core.config import settings
from app.domain.exceptions import (
    PermanentWorkflowError,
    TransientWorkflowError,
)

ENABLED_ENVIRONMENTS = {"development", "test"}
RECOVER_FAILURES = 2


class FailureSimulator:
    """
    Deterministic failure injection for local development.

    Special product IDs trigger known failure scenarios.
    Never enable this behavior in production.
    """

    @staticmethod
    def before_inventory_reservation(
        product_id: str,
        attempt: int,
    ) -> None:
        """``attempt`` is the persisted execution number (1-based), so the
        behavior is identical across worker processes."""
        if settings.ENVIRONMENT not in ENABLED_ENVIRONMENTS:
            return

        if product_id == "SIM-RECOVER" and attempt <= RECOVER_FAILURES:
            raise TransientWorkflowError(
                f"Simulated transient failure on attempt {attempt}"
            )

        if product_id == "SIM-TRANSIENT":
            raise TransientWorkflowError(
                "Simulated inventory service unavailable "
                "before reservation"
            )

        if product_id == "SIM-PERMANENT":
            raise PermanentWorkflowError(
                "Simulated unsupported product"
            )

    @staticmethod
    def lose_inventory_response(
        product_id: str,
        operation_attempt: int,
    ) -> bool:
        """Whether the provider should lose its response after
        committing. Only the operation's first attempt is affected, so a
        later execution (for example after reconciliation fails over to a
        re-run) behaves like a healthy provider."""
        return (
            settings.ENVIRONMENT in ENABLED_ENVIRONMENTS
            and product_id == "SIM-UNCERTAIN"
            and operation_attempt == 1
        )

    @staticmethod
    def before_invoice_generation(product_id: str) -> None:
        """Fails AFTER inventory was reserved, so the order can never
        complete and its stock stays held until it is compensated."""
        if settings.ENVIRONMENT not in ENABLED_ENVIRONMENTS:
            return

        if product_id == "SIM-INVOICE-FAIL":
            raise PermanentWorkflowError(
                "Simulated invoicing system rejected the order"
            )
