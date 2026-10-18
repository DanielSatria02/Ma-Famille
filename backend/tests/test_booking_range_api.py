from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
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


def _court(client, venue_name="GOR"):
    venue = client.post("/v1/venues", json={"name": venue_name, "address": "Jkt"}).json()
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
    # 2026-10-19 is a Monday; defaults open 08:00-22:00.
    client.post(
        "/v1/slots/generate",
        json={
            "court_public_id": court["public_id"],
            "from_day": "2026-10-19",
            "to_day": "2026-10-20",
        },
    )
    return court


def _range(court, start="2026-10-19T09:00:00", end="2026-10-19T12:00:00"):
    return {
        "court_public_id": court["public_id"],
        "starts_at": start,
        "ends_at": end,
        "customer_name": "Budi",
        "customer_contact": "0812",
    }


def test_range_booking_groups_consecutive_hours():
    client = _client()
    try:
        court = _court(client)
        created = client.post("/v1/bookings/range", json=_range(court))
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["hours"] == 3
        assert body["total"] == 300000
        assert len(body["bookings"]) == 3
        assert {b["group_public_id"] for b in body["bookings"]} == {
            body["group_public_id"]
        }
        assert {b["status"] for b in body["bookings"]} == {"pending"}

        day = client.get(
            "/v1/availability/hours",
            params={"court_public_id": court["public_id"], "day": "2026-10-19"},
        ).json()
        by_hour = {entry["hour"]: entry["status"] for entry in day["hours"]}
        assert [by_hour[hour] for hour in (9, 10, 11)] == ["booked"] * 3
        assert by_hour[12] == "available"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_range_booking_conflicts_are_409():
    client = _client()
    try:
        court = _court(client)
        client.post("/v1/bookings/range", json=_range(court))

        same = client.post("/v1/bookings/range", json=_range(court))
        assert same.status_code == 409
        assert same.json()["detail"] == "slot at 09:00 is booked"

        overlap = client.post(
            "/v1/bookings/range", json=_range(court, "2026-10-19T11:00:00", "2026-10-19T14:00:00")
        )
        assert overlap.status_code == 409
        assert overlap.json()["detail"] == "slot at 11:00 is booked"

        # A day without generated slots reports the missing hour instead.
        missing = client.post(
            "/v1/bookings/range", json=_range(court, "2026-10-21T09:00:00", "2026-10-21T11:00:00")
        )
        assert missing.status_code == 409
        assert missing.json()["detail"] == "no slot for 09:00"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_range_booking_validates_input():
    client = _client()
    try:
        court = _court(client)
        not_whole_hour = client.post(
            "/v1/bookings/range", json=_range(court, "2026-10-19T09:00:00", "2026-10-19T11:30:00")
        )
        assert not_whole_hour.status_code == 422

        backwards = client.post(
            "/v1/bookings/range", json=_range(court, "2026-10-19T12:00:00", "2026-10-19T09:00:00")
        )
        assert backwards.status_code == 422

        overnight = client.post(
            "/v1/bookings/range", json=_range(court, "2026-10-19T22:00:00", "2026-10-20T02:00:00")
        )
        assert overnight.status_code == 422

        unknown = client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": "00000000-0000-0000-0000-000000000000",
                "starts_at": "2026-10-19T09:00:00",
                "ends_at": "2026-10-19T10:00:00",
                "customer_name": "Budi",
                "customer_contact": "0812",
            },
        )
        assert unknown.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_cancel_group_frees_every_hour():
    client = _client()
    try:
        court = _court(client)
        group = client.post("/v1/bookings/range", json=_range(court)).json()

        cancelled = client.post(f"/v1/bookings/groups/{group['group_public_id']}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert {b["status"] for b in cancelled.json()} == {"cancelled"}

        day = client.get(
            "/v1/availability/hours",
            params={"court_public_id": court["public_id"], "day": "2026-10-19"},
        ).json()
        by_hour = {entry["hour"]: entry["status"] for entry in day["hours"]}
        assert [by_hour[hour] for hour in (9, 10, 11)] == ["available"] * 3

        assert (
            client.post(
                "/v1/bookings/groups/00000000-0000-0000-0000-000000000000/cancel"
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_range_booking_respects_lead_time(monkeypatch):
    client = _client()
    try:
        monkeypatch.setattr(settings, "booking_min_lead_days", 1)
        today = date.today().isoformat()
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
                "from_day": today,
                "to_day": today,
            },
        )
        early = client.post(
            "/v1/bookings/range",
            json=_range(court, f"{today}T09:00:00", f"{today}T10:00:00"),
        )
        assert early.status_code == 422
        assert early.json()["detail"] == "bookings must be made at least 1 day(s) in advance"
    finally:
        app.dependency_overrides.pop(get_db, None)
