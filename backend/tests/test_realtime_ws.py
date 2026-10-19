"""A booking change is pushed, not polled.

The payment page used to ask the server every few seconds whether its booking
had settled. These tests pin the two things that make the push actually work,
both of which are invisible until they break:

- a change made from a *sync* route reaches an open socket. FastAPI runs sync
  handlers in a threadpool with no running loop, so a publish that only knew
  how to hand work to its own loop dropped every real change silently — the
  socket stayed connected and the client still saw the old status.
- a socket cannot hold the server open at shutdown, which showed up as the
  whole API going unresponsive after a dev reload.
"""

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import realtime
from app.db.base import Base
from app.db.session import get_db
from app.main import app

DAY = "2026-11-09"


def _client() -> TestClient:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    def override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    client.testing_session = TestingSession
    return client


def _venue_court(client: TestClient) -> dict:
    venue = client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()
    court = client.post(
        "/v1/courts",
        json={
            "venue_public_id": venue["public_id"],
            "name": "C1",
            "sport": "padel",
            "price_weekday": 100000,
            "price_weekend": 150000,
        },
    ).json()
    client.post(
        "/v1/slots/generate",
        json={"court_public_id": court["public_id"], "from_day": DAY, "to_day": DAY},
    )
    return {"venue": venue, "court": court}


def _book(client: TestClient, court: dict) -> dict:
    day = client.get(
        "/v1/availability/hours",
        params={"court_public_id": court["public_id"], "day": DAY},
    ).json()
    free = next(h for h in day["hours"] if h["status"] == "available")
    starts_at = free["starts_at"]
    hour = int(starts_at[11:13])
    return client.post(
        "/v1/bookings/range",
        json={
            "court_public_id": court["public_id"],
            "starts_at": starts_at,
            "ends_at": f"{DAY}T{hour + 1:02d}:00:00",
            "customer_name": "Ana",
            "customer_contact": "0812000001",
        },
    ).json()


def test_a_change_from_a_sync_route_reaches_a_waiting_subscriber():
    """The regression this exists for.

    `notify_booking_changed` is called from sync endpoints, which run in a
    threadpool — no running loop there. Before the loop was captured, the
    publish returned early and the waiting queue never received anything.
    """
    public_id = "11111111-1111-1111-1111-111111111111"
    received: asyncio.Queue = asyncio.Queue()

    async def scenario():
        loop = asyncio.get_running_loop()
        queue = realtime.subscribe(realtime.booking_topic(public_id))

        # No running loop for this part: this is the threadpool a sync handler
        # runs on, so `get_running_loop()` raises exactly as it does in prod.
        def from_a_worker():
            assert asyncio._get_running_loop() is None, "expected no loop here"
            realtime.publish_threadsafe(public_id, lambda: {"status": "cancelled"})

        await loop.run_in_executor(None, from_a_worker)
        payload = await asyncio.wait_for(queue.get(), timeout=2)
        realtime.unsubscribe(realtime.booking_topic(public_id), queue)
        return payload

    payload = asyncio.run(scenario())
    received.put_nowait(payload)
    assert received.get_nowait()["status"] == "cancelled"


def test_publishing_to_an_unwatched_booking_is_harmless():
    """Nobody connected is the normal case, not an error."""
    realtime.publish_threadsafe(
        "22222222-2222-2222-2222-222222222222", lambda: {"status": "paid"}
    )


def test_a_full_subscriber_is_dropped_rather_than_blocking_the_writer():
    """A client that stopped reading must not stall a gateway webhook."""
    public_id = "33333333-3333-3333-3333-333333333333"
    topic = realtime.booking_topic(public_id)

    async def scenario():
        queue = realtime.subscribe(topic)
        # Fill it past its bound. `put_nowait` raises once full, which is how
        # the queue reached capacity.
        for _ in range(queue.maxsize):
            queue.put_nowait({"status": "x"})
        # This must not raise even though the queue is full: a client that
        # stopped reading gets dropped, not the writer blocked.
        realtime.publish(topic, {"status": "paid"})
        realtime.unsubscribe(topic, queue)

    asyncio.run(scenario())


def test_the_socket_opens_with_the_current_status(client: TestClient = None):
    """A client that connects late still gets the current state first."""
    client = _client()
    booked = _book(client, _venue_court(client)["court"])
    booking_id = booked["bookings"][0]["public_id"]

    with client.websocket_connect(f"/v1/ws/bookings/{booking_id}") as ws:
        first = ws.receive_json()
    assert first["public_id"] == booking_id
    assert first["status"] in ("pending", "confirmed")


def test_an_unknown_booking_is_closed_rather_than_left_hanging():
    client = _client()
    # The server answers with a close frame, not a first message: a client that
    # guessed an id must not sit on an open socket waiting for data that will
    # never come.
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect(
        "/v1/ws/bookings/44444444-4444-4444-4444-444444444444"
    ) as ws:
        try:
            ws.receive_json()
        except WebSocketDisconnect as exc:
            assert exc.code == 4404
        else:
            raise AssertionError("expected a close for an unknown booking")