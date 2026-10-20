from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.realtime import close_open_sockets
from app.api.v1.router import router as v1_router
from app.core.audit_middleware import AuditMiddleware
from app.core.config import settings
from app.core.crash_handler import CrashHandlerMiddleware
from app.schemas.health import RootResponse

DESCRIPTION = """Sports Venue Booking API (padel courts).

Venues, courts, slots, bookings, payments and the manager dashboard are
wired to the store. `POST /payments` needs DOKU sandbox keys, otherwise it
answers 501 — everything else is live.
"""

OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness and readiness probes."},
    {"name": "venues", "description": "Venue CRUD (writes: manager) + public list."},
    {"name": "courts", "description": "Courts with weekday/weekend rates."},
    {"name": "slots", "description": "Availability calendar per court per day."},
    {
        "name": "bookings",
        "description": "Booking with conflict check, history, confirm/cancel.",
    },
    {"name": "payments", "description": "Deposit/paid via DOKU sandbox + webhook."},
    {"name": "manager", "description": "Incoming bookings + occupancy chart."},
]


def create_app() -> FastAPI:
    # Long-lived WebSocket handlers must be dropped on the way down. Without
    # this a handler parked on `queue.get()` looks like a request that never
    # finishes, and a reload waits for it — the whole API goes unresponsive.
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await close_open_sockets()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        root_path=settings.root_path,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Paged list endpoints put their row count here so the client can
        # render "load more" without changing the response body shape.
        expose_headers=["X-Total-Count"],
    )

    @app.get("/", summary="Root info", response_model=RootResponse, tags=["health"])
    def root() -> RootResponse:
        return RootResponse(service=settings.app_name, env=settings.app_env)

    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    # Records every successful write under /v1/ so the trail cannot drift out of
    # date when a new endpoint is added.
    app.add_middleware(AuditMiddleware)

    # Added last, so it is the outermost middleware and sees a crash before
    # anything else does. A crash answered by Starlette's plain-text 500
    # carries no CORS headers, so the browser blocks it and the client reads
    # the failure as "the server is not reachable" — for a crash on a server
    # that was answering fine. See core/crash_handler.py.
    app.add_middleware(CrashHandlerMiddleware)

    # Uploaded venue/court photos. The directory is created on boot so a fresh
    # checkout (and the test client) can serve them without a manual mkdir.
    media_root = Path(settings.media_root)
    media_root.mkdir(parents=True, exist_ok=True)
    app.mount(settings.media_url, StaticFiles(directory=media_root), name="media")

    return app


app = create_app()
