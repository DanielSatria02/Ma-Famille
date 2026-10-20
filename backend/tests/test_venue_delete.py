"""Deleting a club, and what it refuses to delete.

The delete used to crash with a foreign key error whenever the club still
had a court under it, which is every club that has ever been used. The
manager got a 500 and no explanation.

So the rule is now: what the manager owns goes with the club — the courts,
their slots, the opening hours, the closure dates, the discount codes. What
belongs to a customer stays, and the delete is refused with a 409 that says
what is in the way.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.review import Review
from app.models.venue import Venue


@pytest.fixture
def client() -> TestClient:
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
    # conftest blanks the manager secrets, so the manager routes are open.
    return TestClient(app)


def _club_with_court(client: TestClient) -> tuple[str, str]:
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
    return venue["public_id"], court["public_id"]


def test_deleting_a_club_with_a_court_works(client: TestClient):
    """The courts, slots and hours go with it."""
    venue_id, court_id = _club_with_court(client)
    client.post(
        "/v1/slots/generate",
        json={"court_public_id": court_id, "from_day": "2026-10-20", "to_day": "2026-10-20"},
    )
    client.put(
        f"/v1/venues/{venue_id}/hours/3", json={"opens_at": "08:00", "closes_at": "22:00"}
    )

    assert client.delete(f"/v1/venues/{venue_id}").status_code == 204

    assert client.get(f"/v1/venues/{venue_id}").status_code == 404
    assert client.get(f"/v1/courts/{court_id}").status_code == 404
    # The slots that belonged to the court are gone with it.
    slots = client.get(
        "/v1/slots", params={"court_public_id": court_id, "day": "2026-10-20"}
    )
    assert slots.status_code == 404


def test_deleting_a_club_with_a_booking_is_refused(client: TestClient):
    """A booking is the customer's, so the club stays."""
    venue_id, court_id = _club_with_court(client)
    client.post(
        "/v1/slots/generate",
        json={"court_public_id": court_id, "from_day": "2026-10-20", "to_day": "2026-10-20"},
    )
    hours = client.get(
        "/v1/availability/hours",
        params={"court_public_id": court_id, "day": "2026-10-20"},
    ).json()["hours"]
    free = next(h for h in hours if h["status"] == "available")
    booking = client.post(
        "/v1/bookings",
        json={
            "slot_public_id": free["slot_public_id"],
            "customer_name": "Ana",
            "customer_contact": "0812000011",
        },
    )
    assert booking.status_code == 201

    answer = client.delete(f"/v1/venues/{venue_id}")
    assert answer.status_code == 409
    assert "booking" in answer.json()["detail"]
    # The club is still there.
    assert client.get(f"/v1/venues/{venue_id}").status_code == 200


def test_deleting_a_club_with_a_review_is_refused(client: TestClient):
    """A review is the reviewer's, so the club stays."""
    venue_id, _ = _club_with_court(client)
    # A review needs a visit that has already started, so the review itself
    # is faked here — the rule under test is about the delete, not the gate.
    db = next(app.dependency_overrides[get_db]())
    venue = db.scalar(select(Venue).where(Venue.public_id == uuid.UUID(venue_id)))
    db.add(
        Review(
            public_id=uuid.uuid4(),
            venue_id=venue.id,
            customer_contact="0812000099",
            rating=5,
            comment="Nice court",
        )
    )
    db.commit()
    db.close()

    answer = client.delete(f"/v1/venues/{venue_id}")
    assert answer.status_code == 409
    assert "review" in answer.json()["detail"]


def test_deleting_a_club_that_is_already_gone_is_a_404(client: TestClient):
    assert client.delete("/v1/venues/00000000-0000-0000-0000-000000000000").status_code == 404
