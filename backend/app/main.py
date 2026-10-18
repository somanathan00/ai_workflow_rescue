
from fastapi import FastAPI

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.logging import configure_logging
from app.core.middleware import RequestLoggingMiddleware

configure_logging()

app = FastAPI(
    title="AI Workflow Rescue",
    description=(
        "AI-powered workflow failure "
        "investigation and recovery platform"
    ),
    version="0.1.0",
)

app.include_router(
    api_router,
    prefix="/api/v1",
)

app.add_middleware(RequestLoggingMiddleware)
app.include_router(health.router)
