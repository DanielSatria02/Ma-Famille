"""Answer a crash with JSON the browser is allowed to read

An unhandled exception inside a route produces Starlette's plain-text
"Internal Server Error", and that response carries no CORS headers at all.
The browser then blocks it, the client sees a network error with no response
object, and the frontend reports "the server is not reachable" — for a crash
that happened on the server, with the server answering perfectly well.

So the crash is caught here and answered as JSON, with the CORS headers the
browser needs to be allowed to read it. The message says what happened
without saying anything about the internals: the traceback goes to the log,
where it belongs, and the caller gets a request id to quote.
"""

import logging
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class CrashHandlerMiddleware(BaseHTTPMiddleware):
    """Turn an unhandled exception into a JSON answer with CORS headers."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            # The traceback goes to the log; the caller gets a request id.
            request_id = uuid.uuid4().hex[:12]
            logger.exception(
                "unhandled error on %s %s (request %s)",
                request.method,
                request.url.path,
                request_id,
            )
            return _json_error(request, request_id)


def _json_error(request: Request, request_id: str) -> JSONResponse:
    """A JSON 500 that the browser is allowed to read.

    The CORS headers are set by hand because the middleware that normally adds
    them sits above the router and never sees this response: the crash
    happened below it, and the response is built here, after the fact.
    """
    from app.core.config import settings

    origin = request.headers.get("origin")
    headers = {"X-Request-Id": request_id}
    if origin and origin in settings.cors_origins:
        headers["access-control-allow-origin"] = origin
        headers["access-control-allow-credentials"] = "true"
        headers["vary"] = "Origin"

    return JSONResponse(
        status_code=500,
        content={
            "detail": "The server ran into a problem handling this request.",
            "request_id": request_id,
        },
        headers=headers,
    )
