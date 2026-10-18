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
            "name": "Futsal A",
            "sport": "futsal",
            "price_weekday": 100000,
            "price_weekend": 150000,
        },
    ).json()


def _quote(client, court, start, end):
    return client.get(
        "/v1/pricing/quote",
        params={
            "court_public_id": court["public_id"],
            "starts_at": start,
            "ends_at": end,
        },
    )


def test_quote_uses_court_rate_before_slots_exist():
    client = _client()
    try:
        court = _court(client)
        res = _quote(client, court, "2026-10-19T09:00:00", "2026-10-19T12:00:00")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["hours"] == 3
        assert body["hourly_rate"] == 100000
        assert body["total"] == 300000
        assert body["is_bookable"] is True
        assert [entry["hour"] for entry in body["breakdown"]] == [9, 10, 11]
        assert {entry["slot_public_id"] for entry in body["breakdown"]} == {None}

        # Saturday is priced at the weekend rate.
        weekend = _quote(client, court, "2026-10-24T09:00:00", "2026-10-24T11:00:00").json()
        assert weekend["hourly_rate"] == 150000
        assert weekend["total"] == 300000
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_quote_prefers_slot_price_and_flags_taken_hours():
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
        nine = next(slot for slot in slots if slot["starts_at"][11:16] == "09:00")
        client.patch(f"/v1/slots/{nine['public_id']}", json={"price": 120000})

        quoted = _quote(client, court, "2026-10-19T09:00:00", "2026-10-19T11:00:00").json()
        assert quoted["breakdown"][0]["price"] == 120000
        assert quoted["breakdown"][1]["price"] == 100000
        assert quoted["total"] == 220000

        client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": court["public_id"],
                "starts_at": "2026-10-19T10:00:00",
                "ends_at": "2026-10-19T11:00:00",
                "customer_name": "Budi",
                "customer_contact": "0812",
            },
        )
        taken = _quote(client, court, "2026-10-19T10:00:00", "2026-10-19T12:00:00").json()
        assert taken["is_bookable"] is False
        assert taken["breakdown"][0]["status"] == "booked"
        assert taken["breakdown"][1]["status"] == "available"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_quote_rejects_bad_range_and_unknown_court():
    client = _client()
    try:
        court = _court(client)
        same_moment = _quote(client, court, "2026-10-19T09:00:00", "2026-10-19T09:00:00")
        assert same_moment.status_code == 422

        half_hour = _quote(client, court, "2026-10-19T09:00:00", "2026-10-19T11:30:00")
        assert half_hour.status_code == 422

        overnight = _quote(client, court, "2026-10-19T22:00:00", "2026-10-20T01:00:00")
        assert overnight.status_code == 422
        assert (
            client.get(
                "/v1/pricing/quote",
                params={
                    "court_public_id": "00000000-0000-0000-0000-000000000000",
                    "starts_at": "2026-10-19T09:00:00",
                    "ends_at": "2026-10-19T10:00:00",
                },
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
