from fastapi import APIRouter

from app.api.v1.endpoints import auth, investigations, orders, recovery, workflows

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(orders.router)
api_router.include_router(workflows.router)
api_router.include_router(recovery.router)
api_router.include_router(recovery.queue_router)
api_router.include_router(investigations.router)