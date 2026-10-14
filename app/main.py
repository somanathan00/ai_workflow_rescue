
from fastapi import FastAPI

from app.api.v1.router import api_router


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


@app.get("/health/live", tags=["Health"])
def liveness():
    return {"status": "alive"}
