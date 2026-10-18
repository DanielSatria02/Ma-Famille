"""Live booking status over WebSocket.

The payment page used to ask the server every few seconds whether its
booking had settled. That is the wrong shape for the question: the server
already knows the moment a gateway webhook or a manager action lands, so the
client should be told rather than made to keep asking.

The first frame is the current state, so a client that connects after the
change still gets it and a page refresh resumes cleanly. Everything after
that is a push. A booking nobody is watching costs nothing.
"""

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.realtime import (
    booking_topic,
    publish_threadsafe,
    subscribe,
    unsubscribe,
)
from app.models.booking import Booking

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])

# Every open socket, so a shutdown can close them instead of waiting.
#
# A handler parked on `queue.get()` looks like a request that never finishes,
# and a reloading dev server will wait for it — which shows up as the whole API
# going unresponsive after a file change. Nothing should have to be waited on
# to shut down.
_open_sockets: set = set()


async def close_open_sockets() -> None:
    """Called from the app lifespan. Drops every socket rather than waiting."""
    for socket in list(_open_sockets):
        try:
            await socket.close()
        except Exception:  # noqa: BLE001 — it is already going away
            pass
    _open_sockets.clear()


def _booking(db: Session, public_id: UUID) -> Booking | None:
    return db.scalar(select(Booking).where(Booking.public_id == public_id))


def booking_snapshot(public_id: UUID, request=None) -> dict | None:
    """This booking in the same shape `GET /bookings/{id}` returns.

    Built from the shared `_to_response` on purpose: the pushed frame and the
    polled one cannot drift apart, so the client needs no second renderer.

    The session is the one the request would have used. Going straight to
    `SessionLocal()` ignores a `get_db` override, which is how a test (or a
    future per-request database) reads an empty snapshot and sees the socket
    close on it for no reason at all.

    Both imports are deferred: `bookings` imports this module for the notify
    hook, and a module-level import back would close the loop.
    """
    from app.api.v1.bookings import _to_response
    from app.db.session import session_for_request

    db = session_for_request(request)
    try:
        booking = _booking(db, public_id)
        if booking is None:
            return None
        return json.loads(_to_response(db, booking).model_dump_json())
    finally:
        db.close()


def notify_booking_changed(booking: Booking | None) -> None:
    """Broadcast a booking's new state to whoever is watching it.

    Safe from sync code (a gateway webhook, a manager's click): the publish
    hops onto the loop that owns the sockets. An unwatched booking is a no-op.
    """
    if booking is None:
        return
    public_id = booking.public_id

    def build():
        # Re-read rather than trusting the caller's object: the writer may
        # have committed after this snapshot was taken.
        return booking_snapshot(public_id)

    publish_threadsafe(public_id, build)


@router.websocket("/ws/bookings/{public_id}")
async def booking_stream(websocket: WebSocket, public_id: UUID):
    """Push this booking's status until the client goes away.

    Reading a booking is unprivileged — the dashboard and the payment page
    both do it without a token — so the socket is not gated either. It carries
    only what `GET /bookings/{id}` already returns, and a client that can
    guess the id could have read the same row over HTTP.
    """
    topic = booking_topic(public_id)
    # Subscribe before the first read, so a change landing mid-read lands in
    # the queue instead of falling between "current state" and "the stream".
    queue = subscribe(topic)
    await websocket.accept()
    _open_sockets.add(websocket)

    try:
        initial = booking_snapshot(public_id, websocket)
        if initial is None:
            await websocket.close(code=4404, reason="booking not found")
            return
        await websocket.send_json(initial)

        # One reader for the queue. Two would split the messages between them
        # and silently drop half.
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:  # noqa: BLE001 — a broken socket must not take the app down
        logger.exception("booking socket failed for %s", public_id)
    finally:
        unsubscribe(topic, queue)
        _open_sockets.discard(websocket)
