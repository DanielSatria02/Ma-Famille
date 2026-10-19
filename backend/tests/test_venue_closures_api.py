from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

OPEN_DAY = "2026-10-19"  # Monday
CLOSED_DAY = "2026-10-20"  # Tuesday, closed by the tests below


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


def _venue_and_court(client):
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
    return venue, court


def test_a_closure_closes_the_date_it_covers():
    client = _client()
    try:
        venue, court = _venue_and_court(client)

        created = client.post(
            f"/v1/venues/{venue['public_id']}/closures",
            json={"starts_on": CLOSED_DAY, "ends_on": CLOSED_DAY, "reason": "Renovation"},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["days"] == 1
        assert body["reason"] == "Renovation"
        assert body["venue_public_id"] == venue["public_id"]

        listed = client.get(f"/v1/venues/{venue['public_id']}/closures").json()
        assert [entry["public_id"] for entry in listed] == [body["public_id"]]

        shut = client.get(
            "/v1/availability/hours",
            params={"court_public_id": court["public_id"], "day": CLOSED_DAY},
        ).json()
        assert shut["is_closed"] is True
        assert shut["closure_reason"] == "Renovation"
        assert shut["hours"] == []

        open_day = client.get(
            "/v1/availability/hours",
            params={"court_public_id": court["public_id"], "day": OPEN_DAY},
        ).json()
        assert open_day["is_closed"] is False
        assert open_day["closure_reason"] is None

        # Reopening brings the day back.
        removed = client.delete(
            f"/v1/venues/{venue['public_id']}/closures/{body['public_id']}"
        )
        assert removed.status_code == 204
        assert client.get(f"/v1/venues/{venue['public_id']}/closures").json() == []
        assert (
            client.get(
                "/v1/availability/hours",
                params={"court_public_id": court["public_id"], "day": CLOSED_DAY},
            ).json()["is_closed"]
            is False
        )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_slot_generation_skips_closed_days_and_booking_is_refused():
    client = _client()
    try:
        venue, court = _venue_and_court(client)
        client.post(
            f"/v1/venues/{venue['public_id']}/closures",
            json={"starts_on": CLOSED_DAY, "ends_on": CLOSED_DAY, "reason": "Public holiday"},
        )

        generated = client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "from_day": OPEN_DAY,
                "to_day": CLOSED_DAY,
            },
        ).json()
        assert generated["created"] > 0
        assert generated["skipped_closure_days"] == 1

        closed_slots = client.get(
            "/v1/slots",
            params={"court_public_id": court["public_id"], "day": CLOSED_DAY},
        ).json()
        assert closed_slots == []

        # The calendar skips the closed date as well.
        dates = client.get(
            "/v1/availability/dates",
            params={
                "court_public_id": court["public_id"],
                "from_day": OPEN_DAY,
                "to_day": CLOSED_DAY,
            },
        ).json()
        assert [entry["day"] for entry in dates] == [OPEN_DAY]

        # And a booking made before the closure cannot be repeated on it: the
        # hours that were generated earlier are refused too.
        slot = client.get(
            "/v1/slots",
            params={"court_public_id": court["public_id"], "day": OPEN_DAY},
        ).json()[0]
        blocked = client.post(
            "/v1/bookings",
            json={
                "slot_public_id": slot["public_id"],
                "customer_name": "Budi",
                "customer_contact": "0812",
            },
        )
        assert blocked.status_code == 201

        client.post(
            f"/v1/venues/{venue['public_id']}/closures",
            json={"starts_on": OPEN_DAY, "ends_on": OPEN_DAY, "reason": "Emergency"},
        )
        refused = client.post(
            "/v1/bookings",
            json={
                "slot_public_id": client.get(
                    "/v1/slots",
                    params={"court_public_id": court["public_id"], "day": OPEN_DAY},
                ).json()[1]["public_id"],
                "customer_name": "Sari",
                "customer_contact": "0813",
            },
        )
        assert refused.status_code == 409
        assert refused.json()["detail"] == "venue is closed on 2026-10-19 (Emergency)"

        ranged = client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": court["public_id"],
                "starts_at": f"{OPEN_DAY}T09:00:00",
                "ends_at": f"{OPEN_DAY}T10:00:00",
                "customer_name": "Sari",
                "customer_contact": "0813",
            },
        )
        assert ranged.status_code == 409
        assert "venue is closed" in ranged.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_closure_reports_the_bookings_it_puts_at_risk():
    client = _client()
    try:
        venue, court = _venue_and_court(client)
        client.post(
            "/v1/slots/generate",
            json={"court_public_id": court["public_id"], "from_day": OPEN_DAY, "to_day": OPEN_DAY},
        )
        slots = client.get(
            "/v1/slots",
            params={"court_public_id": court["public_id"], "day": OPEN_DAY},
        ).json()
        for slot in slots[:2]:
            client.post(
                "/v1/bookings",
                json={
                    "slot_public_id": slot["public_id"],
                    "customer_name": "Budi",
                    "customer_contact": "0812",
                },
            )

        created = client.post(
            f"/v1/venues/{venue['public_id']}/closures",
            json={
                "starts_on": OPEN_DAY,
                "ends_on": "2026-10-21",
                "reason": "Renovation week",
            },
        ).json()
        assert created["days"] == 3
        assert created["affected_bookings"] == 2
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_bad_closures_and_unknown_ids():
    client = _client()
    try:
        venue, court = _venue_and_court(client)

        assert (
            client.post(
                f"/v1/venues/{venue['public_id']}/closures",
                json={"starts_on": CLOSED_DAY, "ends_on": OPEN_DAY},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/v1/venues/{venue['public_id']}/closures",
                json={"starts_on": OPEN_DAY, "ends_on": "2027-10-01"},
            ).status_code
            == 422
        )
        missing = client.post(
            "/v1/venues/01a14d3b-969b-7084-ab09-760a34d343dc/closures",
            json={"starts_on": OPEN_DAY, "ends_on": OPEN_DAY},
        )
        assert missing.status_code == 404

        created = client.post(
            f"/v1/venues/{venue['public_id']}/closures",
            json={"starts_on": OPEN_DAY, "ends_on": OPEN_DAY},
        ).json()
        assert created["reason"] == ""
        wrong_venue = client.delete(
            f"/v1/venues/{court['public_id']}/closures/{created['public_id']}"
        )
        assert wrong_venue.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
