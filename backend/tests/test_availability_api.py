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


def _court(client):
    venue = client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()
    return client.post(
        "/v1/courts",
        json={
            "venue_public_id": venue["public_id"],
            "name": "C1",
            "sport": "padel",
            "price_weekday": 100000,
            "price_weekend": 150000,
        },
    ).json()


def test_day_hours_report_every_opening_hour():
    client = _client()
    try:
        court = _court(client)
        # No slots yet: the client still sees the window, every hour unavailable.
        empty = client.get(
            "/v1/availability/hours",
            params={"court_public_id": court["public_id"], "day": "2026-10-19"},
        ).json()
        assert empty["is_closed"] is False
        assert empty["opens_at"] == "08:00"
        assert empty["closes_at"] == "22:00"
        assert [entry["hour"] for entry in empty["hours"]] == list(range(8, 22))
        assert {entry["status"] for entry in empty["hours"]} == {"unavailable"}

        client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-19",
                "to_day": "2026-10-19",
            },
        )
        filled = client.get(
            "/v1/availability/hours",
            params={"court_public_id": court["public_id"], "day": "2026-10-19"},
        ).json()
        assert {entry["status"] for entry in filled["hours"]} == {"available"}
        assert filled["hours"][0]["price"] == 100000
        assert filled["hours"][0]["slot_public_id"] is not None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_booked_hour_shows_as_booked():
    client = _client()
    try:
        court = _court(client)
        client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-19",
                "to_day": "2026-10-19",
            },
        )
        slots = client.get(
            "/v1/slots",
            params={"court_public_id": court["public_id"], "day": "2026-10-19"},
        ).json()
        client.post(
            "/v1/bookings",
            json={
                "slot_public_id": slots[2]["public_id"],
                "customer_name": "Budi",
                "customer_contact": "0812",
            },
        )

        day = client.get(
            "/v1/availability/hours",
            params={"court_public_id": court["public_id"], "day": "2026-10-19"},
        ).json()
        by_hour = {entry["hour"]: entry for entry in day["hours"]}
        assert by_hour[10]["status"] == "booked"
        assert by_hour[9]["status"] == "available"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_date_summary_only_covers_days_with_slots():
    client = _client()
    try:
        court = _court(client)
        client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-19",
                "to_day": "2026-10-20",
            },
        )
        slots = client.get(
            "/v1/slots",
            params={"court_public_id": court["public_id"], "day": "2026-10-19"},
        ).json()
        client.post(
            "/v1/bookings",
            json={
                "slot_public_id": slots[0]["public_id"],
                "customer_name": "Budi",
                "customer_contact": "0812",
            },
        )

        points = client.get(
            "/v1/availability/dates",
            params={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-18",
                "to_day": "2026-10-21",
            },
        ).json()
        assert [point["day"] for point in points] == ["2026-10-19", "2026-10-20"]
        assert points[0] == {
            "day": "2026-10-19",
            "total_hours": 14,
            "booked_hours": 1,
            "free_hours": 13,
        }
        assert points[1]["booked_hours"] == 0
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_closed_day_has_no_hours():
    client = _client()
    try:
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
        client.put(
            f"/v1/venues/{venue['public_id']}/hours/6",
            json={"opens_at": "08:00", "closes_at": "22:00", "is_closed": True},
        )
        sunday = client.get(
            "/v1/availability/hours",
            params={"court_public_id": court["public_id"], "day": "2026-10-25"},
        ).json()
        assert sunday["is_closed"] is True
        assert sunday["hours"] == []
        assert sunday["opens_at"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_availability_guards():
    client = _client()
    try:
        court = _court(client)
        backwards = client.get(
            "/v1/availability/dates",
            params={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-20",
                "to_day": "2026-10-19",
            },
        )
        assert backwards.status_code == 422

        too_wide = client.get(
            "/v1/availability/dates",
            params={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-19",
                "to_day": "2027-10-19",
            },
        )
        assert too_wide.status_code == 422

        unknown = client.get(
            "/v1/availability/hours",
            params={
                "court_public_id": "00000000-0000-0000-0000-000000000000",
                "day": "2026-10-19",
            },
        )
        assert unknown.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
