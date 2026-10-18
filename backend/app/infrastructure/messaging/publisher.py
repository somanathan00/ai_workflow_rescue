
from uuid import UUID

from app.workers.order_tasks import process_order


class WorkflowPublisher:

    @staticmethod
    def publish_order(workflow_id: UUID) -> str:
        result = process_order.apply_async(
            args=[str(workflow_id)],
            queue="workflow",
        )
        return result.id
