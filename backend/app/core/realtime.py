"""A tiny in-process pub/sub for pushing booking changes to open sockets.

The payment page used to ask the server every five seconds whether its
booking had settled. That is the wrong shape for the question: the server
already learns the answer the moment a gateway webhook or a manager action
lands, so the client should be *told*, not made to guess when to ask again.

This broker is deliberately in-process. It has no opinion about scaling out:
on one worker (dev, or a small deployment) it is exactly right and costs no
dependency. If the app ever runs several workers, this is the one module that
has to be swapped for a shared bus — everything else keeps the same interface.

Subscribers are plain async callbacks. A slow or dead client is dropped
rather than allowed to stall the writer, because a payment webhook must never
wait on a browser.
"""

import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import Callable
from uuid import UUID

logger = logging.getLogger(__name__)

# topic (a booking's public id, as text) -> set of queue-feeding tasks.
_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

# The loop that owns the sockets, captured the first time one subscribes.
#
# Writers are mostly sync endpoints — a manager's click, a gateway webhook —
# and FastAPI runs those in a threadpool, where there is no running loop to
# hand work to. Publishing from a worker therefore has to hop back onto the
# loop recorded here; without it every change made from a sync route was
# dropped silently and only the opening frame reached the client.
_loop: asyncio.AbstractEventLoop | None = None


def bind_loop() -> None:
    """Remember the loop that owns the sockets. Call from async code."""
    global _loop
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        pass


def publish_threadsafe(booking_public_id, snapshot: Callable[[], dict]) -> None:
    """Publish a booking's state from anywhere, including a sync handler.

    Already on the loop: publish inline. On a worker: hop back to the loop
    that owns the sockets. No loop at all (a CLI, a sync worker with no
    sockets): nothing is listening, so this is a no-op rather than an error.
    """
    if booking_topic(booking_public_id) not in _subscribers:
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        publish_booking(booking_public_id, snapshot)
        return
    if _loop is not None and not _loop.is_closed():
        _loop.call_soon_threadsafe(
            lambda: publish_booking(booking_public_id, snapshot)
        )


def subscribe(topic: str) -> asyncio.Queue:
    """A queue that will receive every payload published to `topic`.

    Binding the loop here is what makes a publish from a sync request handler
    possible: the socket is the only place a running loop is guaranteed.
    """
    bind_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers[topic].add(queue)
    return queue


def unsubscribe(topic: str, queue: asyncio.Queue) -> None:
    with contextlib.suppress(KeyError):
        _subscribers[topic].discard(queue)
    with contextlib.suppress(KeyError):
        if not _subscribers[topic]:
            del _subscribers[topic]


def publish(topic: str, payload: dict) -> None:
    """Tell everyone watching `topic`. Never raises, never blocks.

    A queue that is full means a client stopped reading; that client is
    dropped so the writer (a webhook, a manager's click) carries on.
    """
    watchers = _subscribers.get(topic)
    if not watchers:
        return
    for queue in list(watchers):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("dropping a booking subscriber that stopped reading")
            watchers.discard(queue)


def booking_topic(booking_public_id: UUID | str) -> str:
    """The topic a booking's changes are published on."""
    return f"booking:{booking_public_id}"


def publish_booking(booking_public_id: UUID | str, snapshot: Callable[[], dict] | dict):
    """Broadcast a booking's state to whoever is watching it.

    `snapshot` may be the payload itself or a callable that builds it — the
    callable form lets the caller defer building it until there is someone to
    receive it, so an unwatched booking costs one dict lookup.
    """
    topic = booking_topic(booking_public_id)
    if topic not in _subscribers:
        return
    payload = snapshot() if callable(snapshot) else snapshot
    if payload is not None:
        publish(topic, payload)
