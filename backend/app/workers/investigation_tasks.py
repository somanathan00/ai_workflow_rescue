from uuid import UUID

from app.infrastructure.database.session import SessionLocal
from app.services.investigation_service import InvestigationService
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.investigation_tasks.run_investigation")
def run_investigation(investigation_id: str) -> None:
    with SessionLocal() as db:
        InvestigationService.run(db, UUID(investigation_id))
