"""A booking made while signed in belongs to the account.

Before accounts a customer was only the contact string typed into the form,
so the same person with a typo owned a different history, and guessing a
number reached someone else's visits. These tests pin what the token changes:

- a signed-in booking carries the account, and cannot be aimed at another;
- "my bookings" needs no contact when the token says who is asking;
- cancelling works off the account, which a typo cannot fake;
- a booking without a token behaves exactly as it did before.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.booking import Booking

# A weekday, far enough from today that the lead-time rule never bites.
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


def _first_free_slot(client: TestClient, court_id: str) -> dict:
    """The first open hour of the day, as the booking body wants it.

    `/availability/hours` answers a DayHoursResponse — the hours live under
    `hours`. Each entry carries only `starts_at`, not an end: slots are whole
    hours, so the end is the next hour's start.
    """
    day = client.get(
        "/v1/availability/hours",
        params={"court_public_id": court_id, "day": DAY},
    ).json()
    free = [row for row in day["hours"] if row["status"] == "available"]
    assert free, f"expected an open hour that day, got {day}"
    starts_at = free[0]["starts_at"]
    hour = int(starts_at[11:13])
    return {"starts_at": starts_at, "ends_at": f"{DAY}T{hour + 1:02d}:00:00"}


def _sign_in(client: TestClient, email="ana@example.test") -> dict:
    out = client.post(
        "/v1/customers/register",
        json={
            "email": email,
            "password": "correct horse",
            "display_name": "Ana",
            "phone": "0812000001",
        },
    )
    assert out.status_code == 201, out.text
    return {"X-Customer-Token": out.json()["token"]}


def _book(client: TestClient, court_id: str, slot: dict, headers=None, **extra):
    body = {
        "court_public_id": court_id,
        "starts_at": slot["starts_at"],
        "ends_at": slot["ends_at"],
        "customer_name": extra.pop("customer_name", "Ana"),
        "customer_contact": extra.pop("customer_contact", "0812000001"),
    }
    body.update(extra)
    return client.post("/v1/bookings/range", json=body, headers=headers or {})


def _stored_customer_ids(client: TestClient) -> list:
    db = client.testing_session()
    rows = db.scalars(select(Booking)).all()
    ids = [row.customer_id for row in rows]
    db.close()
    return ids


def test_a_signed_in_booking_carries_the_account():
    client = _client()
    court = _venue_court(client)["court"]
    headers = _sign_in(client)
    slot = _first_free_slot(client, court["public_id"])

    out = _book(client, court["public_id"], slot, headers=headers)
    assert out.status_code == 201, out.text
    assert set(_stored_customer_ids(client)) != {None}


def test_a_booking_without_a_token_has_no_account():
    """The walk-up path must be untouched: no token, no account, still books."""
    client = _client()
    court = _venue_court(client)["court"]
    slot = _first_free_slot(client, court["public_id"])

    out = _book(client, court["public_id"], slot)
    assert out.status_code == 201, out.text
    assert set(_stored_customer_ids(client)) == {None}


def test_an_unknown_token_does_not_block_the_booking():
    """A stale browser tab must not cost someone their booking."""
    client = _client()
    court = _venue_court(client)["court"]
    slot = _first_free_slot(client, court["public_id"])

    out = _book(
        client, court["public_id"], slot, headers={"X-Customer-Token": "not-a-token"}
    )
    assert out.status_code == 201, out.text
    assert set(_stored_customer_ids(client)) == {None}


def test_the_token_decides_the_account_not_the_body():
    """There is no field for it: a client cannot book against someone else."""
    client = _client()
    court = _venue_court(client)["court"]
    headers = _sign_in(client)
    slot = _first_free_slot(client, court["public_id"])

    out = _book(
        client,
        court["public_id"],
        slot,
        headers=headers,
        customer_id=999,
        customer_public_id="00000000-0000-0000-0000-000000000000",
    )
    assert out.status_code == 201, out.text
    assert 999 not in _stored_customer_ids(client)


def test_my_bookings_needs_no_contact_when_signed_in():
    client = _client()
    court = _venue_court(client)["court"]
    headers = _sign_in(client)
    _book(client, court["public_id"], _first_free_slot(client, court["public_id"]), headers=headers)

    out = client.get("/v1/bookings", headers=headers)
    assert out.status_code == 200, out.text
    assert len(out.json()) == 1


def test_the_account_list_ignores_the_contact_when_both_are_given():
    """A signed-in customer listing someone else's contact still sees only
    their own visits — the account wins, so the contact cannot widen it."""
    client = _client()
    court = _venue_court(client)["court"]
    headers = _sign_in(client)
    _book(client, court["public_id"], _first_free_slot(client, court["public_id"]), headers=headers)

    out = client.get(
        "/v1/bookings",
        params={"customer_contact": "0812999999"},
        headers=headers,
    )
    assert out.status_code == 200
    assert len(out.json()) == 1


def test_a_contact_lookup_still_works_without_an_account():
    """Bookings made before accounts, or without signing in, stay reachable."""
    client = _client()
    court = _venue_court(client)["court"]
    _book(
        client,
        court["public_id"],
        _first_free_slot(client, court["public_id"]),
        customer_contact="0812000002",
    )

    out = client.get("/v1/bookings", params={"customer_contact": "0812000002"})
    assert out.status_code == 200
    assert len(out.json()) == 1


def test_history_refuses_when_there_is_no_account_and_no_contact():
    """Before, the contact was required by the query string; now that either
    can identify the caller, asking for neither is an error, not a listing."""
    client = _client()
    out = client.get("/v1/bookings")
    assert out.status_code == 422


def test_a_signed_in_customer_can_cancel_without_the_contact():
    client = _client()
    court = _venue_court(client)["court"]
    headers = _sign_in(client)
    booked = _book(
        client, court["public_id"], _first_free_slot(client, court["public_id"]), headers=headers
    ).json()
    group = booked["group_public_id"]

    out = client.post(f"/v1/bookings/groups/{group}/cancel", headers=headers)
    assert out.status_code == 200, out.text
    assert all(row["status"] == "cancelled" for row in out.json())


def test_another_account_cannot_cancel_a_visit(monkeypatch):
    client = _client()
    # Venue/court creation is a manager route, so the password is set after
    # they exist: with none, dev mode leaves those routes open.
    court = _venue_court(client)["court"]
    monkeypatch.setattr(settings, "manager_password", "kata-sandi")
    mine = _sign_in(client, email="ana@example.test")
    theirs = _sign_in(client, email="betty@example.test")
    booked = _book(
        client, court["public_id"], _first_free_slot(client, court["public_id"]), headers=mine
    ).json()
    group = booked["group_public_id"]

    out = client.post(f"/v1/bookings/groups/{group}/cancel", headers=theirs)
    assert out.status_code == 403


def test_cancel_still_needs_some_kind_of_proof(monkeypatch):
    client = _client()
    # Password set after the manager-owned setup, as above.
    court = _venue_court(client)["court"]
    monkeypatch.setattr(settings, "manager_password", "kata-sandi")
    booked = _book(
        client, court["public_id"], _first_free_slot(client, court["public_id"])
    ).json()
    group = booked["group_public_id"]

    out = client.post(f"/v1/bookings/groups/{group}/cancel")
    assert out.status_code == 403
