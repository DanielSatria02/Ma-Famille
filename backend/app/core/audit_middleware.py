"""HTTP middleware that writes the audit trail.

Recording at the request layer (rather than inside every handler) means the
trail cannot silently fall out of date when someone adds a new write endpoint:
if it mutates state and answers 2xx, it is logged.

The row is best-effort. A failed audit write is logged and swallowed — the
business response is already on its way to the client and must not be turned
into a 500 because the trail could not be saved.
"""

import logging
import re
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.security import is_manager
from app.db.session import SessionLocal, get_db
from app.services import audit as audit_service

logger = logging.getLogger(__name__)

# Only these methods change state; GET/HEAD/OPTIONS are reads.
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)

# /v1/<resource>/<id>/<sub-action>  →  action "<resource>.<sub-action>"
# /v1/<resource>/<id>               →  action "<resource>.<verb>"
# The verb is derived from the HTTP method so `PATCH /venues/{id}` reads as
# `venue.update`, not `venue.patch`.
METHOD_VERB = {"POST": "create", "PUT": "set", "PATCH": "update", "DELETE": "delete"}

# English plural → the singular entity name used in the trail.
_SINGULAR = {
    "venues": "venue",
    "courts": "court",
    "slots": "slot",
    "bookings": "booking",
    "payments": "payment",
    "notifications": "notification",
    "closures": "closure",
    "hours": "hours",
    "photos": "photo",
}


def _resource_and_action(path: str, method: str) -> tuple[str, str, str | None]:
    """Turn a request path into (entity_type, action, entity_public_id).

    Works with or without a root_path prefix by anchoring on `/v1/`.
    """
    idx = path.find("/v1/")
    tail = path[idx + 4 :] if idx >= 0 else path.strip("/")
    segments = [s for s in tail.split("/") if s]

    resource = segments[0] if segments else "unknown"
    entity_type = _SINGULAR.get(resource, resource.rstrip("s") or resource)

    # A UUID anywhere in the path identifies the row that was touched.
    public_id = None
    for seg in segments:
        if _UUID.fullmatch(seg):
            public_id = seg
            break

    # A trailing sub-action (…/refund, …/confirm, …/mark-paid) is more
    # descriptive than the HTTP verb, so prefer it when present.
    verb = METHOD_VERB.get(method, method.lower())
    if len(segments) >= 3 and segments[-1] and not _UUID.fullmatch(segments[-1]):
        action = f"{entity_type}.{segments[-1]}"
    else:
        action = f"{entity_type}.{verb}"
    return entity_type, action, public_id


def _actor(request: Request) -> str:
    """Who made the change: a manager (valid token) or a customer."""
    token = request.headers.get("X-Manager-Token")
    if token and is_manager(token):
        return "manager"
    return "customer"


class AuditMiddleware(BaseHTTPMiddleware):
    """Log every successful state-changing request under /v1/."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._prefix = settings.api_v1_prefix.rstrip("/")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        if request.method not in WRITE_METHODS:
            return response
        # Only the versioned API; the root probe and /media are not domain writes.
        if self._prefix and not request.url.path.startswith(self._prefix):
            return response
        # Client/validation errors changed nothing worth recording.
        if response.status_code >= 400:
            return response

        try:
            entity_type, action, public_id = _resource_and_action(
                request.url.path, request.method
            )
            # Open its own session: the request-scoped one is already closed by
            # the time this runs, and the trail must survive the caller's
            # rollback. Honour a get_db override so tests (and any future
            # multi-tenant setup) log to the same database they read from.
            factory = self._session_factory(request)
            db = next(factory())
            try:
                audit_service.record(
                    db,
                    actor=_actor(request),
                    action=action,
                    entity_type=entity_type,
                    entity_public_id=public_id,
                )
            finally:
                db.close()
        except Exception:  # noqa: BLE001 — never let the trail break a response
            logger.exception("audit middleware failed for %s %s", request.method, request.url.path)

        return response

    @staticmethod
    def _session_factory(request: Request) -> Callable[[], object]:
        """The generator that yields a DB session, override-aware.

        `get_db` is the app-wide session dependency; when it is overridden
        (FastAPI dependency_overrides), the audit row must go to that same
        database or it would land somewhere the caller cannot read it back.
        """
        override = request.app.dependency_overrides.get(get_db)
        if override is not None:
            return override
        return SessionLocal
