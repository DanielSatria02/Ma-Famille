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


def _court_with_slots(client):
    venue = client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()
    court = client.post(
        "/v1/courts",
        json={
            "venue_public_id": venue["public_id"],
            "name": "C1",
            "sport": "futsal",
            "price_weekday": 100000,
            "price_weekend": 150000,
        },
    ).json()
    client.post(
        "/v1/slots/generate",
        json={
            "court_public_id": court["public_id"],
            "from_day": "2026-10-19",
            "to_day": "2026-10-21",
        },
    )
    return court


def _book(client, court, day, start, end, name="Budi"):
    return client.post(
        "/v1/bookings/range",
        json={
            "court_public_id": court["public_id"],
            "starts_at": f"{day}T{start}:00",
            "ends_at": f"{day}T{end}:00",
            "customer_name": name,
            "customer_contact": "0812",
        },
    ).json()


def test_manager_bookings_filter_by_day_and_range():
    client = _client()
    try:
        court = _court_with_slots(client)
        _book(client, court, "2026-10-19", "09", "11")
        _book(client, court, "2026-10-21", "14", "15", name="Ani")

        monday = client.get("/v1/manager/bookings", params={"day": "2026-10-19"}).json()
        assert [row["slot"]["starts_at"][11:16] for row in monday] == ["09:00", "10:00"]

        tail = client.get(
            "/v1/manager/bookings",
            params={"from_day": "2026-10-20", "to_day": "2026-10-21"},
        ).json()
        assert [row["customer_name"] for row in tail] == ["Ani"]

        empty = client.get("/v1/manager/bookings", params={"day": "2026-10-20"}).json()
        assert empty == []

        # Slot times stay in order for the dashboard timeline.
        everything = client.get("/v1/manager/bookings").json()
        assert [row["slot"]["starts_at"][11:16] for row in everything] == [
            "09:00",
            "10:00",
            "14:00",
        ]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_manager_bookings_filter_by_status_and_guard_range():
    client = _client()
    try:
        court = _court_with_slots(client)
        booked = _book(client, court, "2026-10-19", "09", "10")
        client.post(f"/v1/bookings/{booked['bookings'][0]['public_id']}/cancel")

        cancelled = client.get(
            "/v1/manager/bookings",
            params={"booking_status": "cancelled", "day": "2026-10-19"},
        ).json()
        assert len(cancelled) == 1

        pending = client.get(
            "/v1/manager/bookings",
            params={"booking_status": "pending", "day": "2026-10-19"},
        ).json()
        assert pending == []

        backwards = client.get(
            "/v1/manager/bookings",
            params={"from_day": "2026-10-20", "to_day": "2026-10-19"},
        )
        assert backwards.status_code == 422

        too_wide = client.get(
            "/v1/manager/bookings",
            params={"from_day": "2026-10-19", "to_day": "2027-10-19"},
        )
        assert too_wide.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)
