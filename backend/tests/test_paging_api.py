"""Paging: list endpoints slice the same JSON array and report the row total
in an `X-Total-Count` header, so the client can render "load more" without the
response body changing shape.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app


def _client():
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
    return TestClient(app)


def _seed_bookings(client, count: int) -> list[dict]:
    """One venue, one court, `count` hourly slots on one day, one booking each."""
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
    slots = client.post(
        "/v1/slots",
        json=[
            {
                "court_public_id": court["public_id"],
                "starts_at": f"2026-10-20T{8 + i:02d}:00:00",
                "ends_at": f"2026-10-20T{9 + i:02d}:00:00",
                "price": 100000,
            }
            for i in range(count)
        ],
    ).json()
    booked = []
    for i, slot in enumerate(slots):
        res = client.post(
            "/v1/bookings",
            json={
                "slot_public_id": slot["public_id"],
                "customer_name": f"Guest {i}",
                "customer_contact": f"08120000{i:04d}",
            },
        )
        assert res.status_code == 201, res.text
        booked.append(res.json())
    return booked


def test_manager_bookings_paged_with_total_header():
    client = _client()
    try:
        booked = _seed_bookings(client, 3)

        first = client.get("/v1/manager/bookings", params={"limit": 2})
        assert first.status_code == 200
        assert len(first.json()) == 2
        # The header is the whole point: total is the un-sliced row count.
        assert first.headers["X-Total-Count"] == str(len(booked))

        second = client.get("/v1/manager/bookings", params={"limit": 2, "offset": 2})
        assert len(second.json()) == 1
        assert second.headers["X-Total-Count"] == str(len(booked))
        # Pages do not overlap and do cover every row.
        seen = {row["public_id"] for row in first.json()} | {
            row["public_id"] for row in second.json()
        }
        assert seen == {row["public_id"] for row in booked}

        # A narrow page still reports the full total, not the page length.
        tiny = client.get("/v1/manager/bookings", params={"limit": 1})
        assert len(tiny.json()) == 1
        assert tiny.headers["X-Total-Count"] == str(len(booked))
    finally:
        app.dependency_overrides.clear()


def test_manager_bookings_default_page_falls_back_to_page_size():
    client = _client()
    try:
        booked = _seed_bookings(client, 2)
        res = client.get("/v1/manager/bookings")
        assert res.status_code == 200
        # Fewer rows than the default page size: everything comes back, and the
        # header still tells the client how many there were in total.
        assert len(res.json()) == len(booked)
        assert res.headers["X-Total-Count"] == str(len(booked))
    finally:
        app.dependency_overrides.clear()


def test_customer_history_paged_with_total_header():
    client = _client()
    try:
        booked = _seed_bookings(client, 3)
        contact = booked[0]["customer_contact"]

        first = client.get(
            "/v1/bookings",
            params={"customer_contact": contact, "limit": 2},
        )
        assert first.status_code == 200
        # History is by contact, so this one customer has a single booking here.
        assert len(first.json()) == 1
        assert first.headers["X-Total-Count"] == "1"
    finally:
        app.dependency_overrides.clear()


def test_page_size_is_bounded():
    client = _client()
    try:
        _seed_bookings(client, 1)
        # Over the max page size is a validation error, not a silent clamp —
        # a client asking for an unbounded page is a bug worth surfacing.
        res = client.get("/v1/manager/bookings", params={"limit": 10_000})
        assert res.status_code == 422

        # A negative offset is likewise rejected rather than wrapping around.
        res = client.get("/v1/manager/bookings", params={"offset": -1})
        assert res.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_notifications_paged_with_total_header():
    client = _client()
    try:
        _seed_bookings(client, 3)

        first = client.get("/v1/manager/notifications", params={"limit": 2})
        assert first.status_code == 200
        # One outbox row per booking event; at minimum each booking queued one.
        total = int(first.headers["X-Total-Count"])
        assert total >= 3
        assert len(first.json()) == 2

        # The status filter slices and counts the same way.
        queued = client.get("/v1/manager/notifications", params={"status": "queued"})
        # The header counts the filtered set; the body is at most one page of it.
        assert int(queued.headers["X-Total-Count"]) >= len(queued.json())
    finally:
        app.dependency_overrides.clear()
