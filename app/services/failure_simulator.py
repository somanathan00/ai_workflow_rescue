
from app.domain.exceptions import (
    PermanentWorkflowError,
    TransientWorkflowError,
)


class FailureSimulator:
    """
    Deterministic failure injection for local development.

    Special product IDs trigger known failure scenarios.
    Never enable this behavior in production.
    """

    @staticmethod
    def before_inventory_reservation(
        product_id: str,
    ) -> None:
        if product_id == "SIM-TRANSIENT":
            raise TransientWorkflowError(
                "Simulated inventory service unavailable "
                "before reservation"
            )

        if product_id == "SIM-PERMANENT":
            raise PermanentWorkflowError(
                "Simulated unsupported product"
            )
