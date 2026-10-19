from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.booking import Booking


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
    return TestClient(app), TestingSession


def _visit(client):
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
        json={
            "court_public_id": court["public_id"],
            "from_day": "2026-10-19",
            "to_day": "2026-10-19",
        },
    )
    return client.post(
        "/v1/bookings/range",
        json={
            "court_public_id": court["public_id"],
            "starts_at": "2026-10-19T09:00:00",
            "ends_at": "2026-10-19T11:00:00",
            "customer_name": "Budi",
            "customer_contact": "0812",
        },
    ).json()


def _age(Session, minutes):
    """Pretend the booking was made `minutes` ago."""
    with Session() as db:
        for booking in db.query(Booking).all():
            booking.created_at = (
                datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=minutes)
            )
        db.commit()


def test_a_fresh_booking_reports_how_long_it_is_held():
    client, _ = _client()
    try:
        visit = _visit(client)
        ttl_seconds = settings.booking_ttl_minutes * 60

        for booking in visit["bookings"]:
            detail = client.get(f"/v1/bookings/{booking['public_id']}").json()
            assert detail["expires_in_seconds"] is not None
            assert ttl_seconds - 60 < detail["expires_in_seconds"] <= ttl_seconds

        # A settled booking is not "held" any more.
        group = visit["group_public_id"]
        client.post(f"/v1/bookings/groups/{group}/confirm")
        confirmed = client.get(f"/v1/bookings/{visit['bookings'][0]['public_id']}").json()
        assert confirmed["status"] == "confirmed"
        assert confirmed["expires_in_seconds"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_an_old_booking_shows_less_time_left_and_then_expires():
    client, Session = _client()
    try:
        visit = _visit(client)
        booking_id = visit["bookings"][0]["public_id"]
        ttl_seconds = settings.booking_ttl_minutes * 60

        _age(Session, 5)
        young = client.get(f"/v1/bookings/{booking_id}").json()
        assert young["expires_in_seconds"] <= ttl_seconds - 5 * 60 + 5

        # Past the TTL the lazy sweep cancels it and the hold is over.
        _age(Session, settings.booking_ttl_minutes + 1)
        old = client.get(f"/v1/bookings/{booking_id}").json()
        assert old["status"] == "cancelled"
        assert old["expires_in_seconds"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)
