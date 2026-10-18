import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("http")

_WORKFLOW_PATH = re.compile(r"/workflows/([0-9a-fA-F-]{36})")
_QUIET_PATHS = {"/health/live", "/health/ready", "/metrics"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Adds an X-Request-ID and one structured log line per request,
    tagged with ``workflow_id`` when the path names a workflow."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        started = time.monotonic()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            if request.url.path not in _QUIET_PATHS:
                extra = {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
                match = _WORKFLOW_PATH.search(request.url.path)

                if match:
                    extra["workflow_id"] = match.group(1)

                logger.info("http_request", extra=extra)
