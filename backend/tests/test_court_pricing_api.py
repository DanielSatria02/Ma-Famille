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


def _venue(client):
    return client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()


def _court(client, venue, **overrides):
    payload = {
        "venue_public_id": venue["public_id"],
        "name": "Lapangan Padel 1",
        "sport": "padel",
        "kind": "court",
        "price_weekday": 100000,
        "price_weekend": 150000,
    }
    payload.update(overrides)
    return client.post("/v1/courts", json=payload).json()


def test_kind_defaults_and_is_reported():
    client = _client()
    try:
        venue = _venue(client)
        default = _court(client, venue, name="Futsal A")
        assert default["kind"] == "court"

        cafe = _court(client, venue, name="Kopi Corner", kind="cafe")
        assert cafe["kind"] == "cafe"

        office = _court(client, venue, name="Meeting Room", kind="office")
        assert office["kind"] == "office"
        assert {court["kind"] for court in client.get("/v1/courts").json()} == {
            "court",
            "cafe",
            "office",
        }
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_unpriced_facility_is_listed_but_not_bookable():
    client = _client()
    try:
        venue = _venue(client)
        court = _court(client, venue, price_weekday=None, price_weekend=None)
        assert court["is_price_set"] is False
        assert court["price_weekday"] is None

        quoted = client.get(
            "/v1/pricing/quote",
            params={
                "court_public_id": court["public_id"],
                "starts_at": "2026-10-19T09:00:00",
                "ends_at": "2026-10-19T11:00:00",
            },
        ).json()
        assert quoted["is_bookable"] is False
        assert quoted["total"] == 0

        generated = client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-19",
                "to_day": "2026-10-19",
            },
        ).json()
        assert generated["created"] == 0
        assert generated["skipped_unpriced"] == 1

        refused = client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": court["public_id"],
                "starts_at": "2026-10-19T09:00:00",
                "ends_at": "2026-10-19T10:00:00",
                "customer_name": "Budi",
                "customer_contact": "0812",
            },
        )
        assert refused.status_code == 409
        assert refused.json()["detail"] == "court has no rate set for that day"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_pricing_can_be_set_and_reset():
    client = _client()
    try:
        venue = _venue(client)
        court = _court(client, venue, price_weekday=None, price_weekend=None)

        priced = client.patch(
            f"/v1/courts/{court['public_id']}",
            json={"price_weekday": 90000, "price_weekend": 130000},
        ).json()
        assert priced["is_price_set"] is True
        assert priced["price_weekday"] == 90000

        generated = client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-19",
                "to_day": "2026-10-19",
            },
        ).json()
        assert generated["created"] == 14

        # An explicit null resets one day's rate; the other stays untouched.
        reset = client.patch(
            f"/v1/courts/{court['public_id']}", json={"price_weekday": None}
        ).json()
        assert reset["price_weekday"] is None
        assert reset["price_weekend"] == 130000
        assert reset["is_price_set"] is False

        # A rename alone must not wipe the weekend rate.
        renamed = client.patch(
            f"/v1/courts/{court['public_id']}", json={"name": "Futsal B"}
        ).json()
        assert renamed["name"] == "Futsal B"
        assert renamed["price_weekend"] == 130000
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_inactive_facility_cannot_be_booked():
    client = _client()
    try:
        venue = _venue(client)
        court = _court(client, venue)
        client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-19",
                "to_day": "2026-10-19",
            },
        )
        deactivated = client.patch(
            f"/v1/courts/{court['public_id']}", json={"is_active": False}
        ).json()
        assert deactivated["is_active"] is False

        refused = client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": court["public_id"],
                "starts_at": "2026-10-19T09:00:00",
                "ends_at": "2026-10-19T10:00:00",
                "customer_name": "Budi",
                "customer_contact": "0812",
            },
        )
        assert refused.status_code == 409
        assert refused.json()["detail"] == "court is not active"

        quoted = client.get(
            "/v1/pricing/quote",
            params={
                "court_public_id": court["public_id"],
                "starts_at": "2026-10-19T09:00:00",
                "ends_at": "2026-10-19T10:00:00",
            },
        ).json()
        assert quoted["is_bookable"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)
