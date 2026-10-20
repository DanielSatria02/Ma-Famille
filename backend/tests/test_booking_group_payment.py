"""A booking of several hours is bought as one thing.

Two hours booked in one go are two rows that share a group. They are one
purchase: one price, one invoice, one confirmation. The bug this pins down
was that the invoice was raised for one hour while the customer was told to
pay for one hour — so a two-hour booking cost half of what it should have,
and the second hour was left pending, free to expire and be given away.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import payments
from app.db.base import Base
from app.db.session import get_db
from app.main import app

DAY = "2026-11-16"  # a Monday, a weekday, far enough ahead: 100000/hour


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


def _end_of(hour: dict) -> str:
    """The end of an availability hour: one hour after it starts."""
    start = hour["starts_at"]
    return f"{start[:11]}{int(start[11:13]) + 1:02d}:00:00"


def _two_hour_visit(client: TestClient) -> dict:
    """A club, a court and a booked two-hour range."""
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
    hours = client.get(
        "/v1/availability/hours",
        params={"court_public_id": court["public_id"], "day": DAY},
    ).json()["hours"]
    free = [h for h in hours if h["status"] == "available"]
    booked = client.post(
        "/v1/bookings/range",
        json={
            "court_public_id": court["public_id"],
            "starts_at": free[0]["starts_at"],
            "ends_at": _end_of(free[1]),
            "customer_name": "Ana",
            "customer_contact": "0812000011",
        },
    ).json()
    return {"venue": venue, "court": court, "booked": booked}


def test_the_booking_answers_the_price_of_the_whole_visit(client: TestClient):
    data = _two_hour_visit(client)
    assert data["booked"]["hours"] == 2
    assert data["booked"]["total"] == 200000

    first = data["booked"]["bookings"][0]
    answer = client.get(f"/v1/bookings/{first['public_id']}").json()
    # The hour still costs one hour's price...
    assert answer["total"] == 100000
    # ...but the visit is priced as a whole.
    assert answer["group_total"] == 200000
    assert answer["group_hours"] == 2
    assert answer["group_starts_at"] is not None
    assert answer["group_ends_at"] is not None


def test_a_full_payment_charges_the_whole_visit(client: TestClient, monkeypatch):
    """The amount in the body is advisory for a full payment."""
    data = _two_hour_visit(client)
    first = data["booked"]["bookings"][0]

    charged = {}

    def fake_checkout(**kwargs):
        charged["amount"] = kwargs["amount"]
        from app.services.doku import CheckoutResult

        return CheckoutResult(
            invoice_number=kwargs["invoice_number"],
            checkout_url="https://pay.test/x",
            token_id="tok",
        )

    monkeypatch.setattr(payments.doku, "create_checkout", fake_checkout)

    # The client only knows about the first hour and asks for that much.
    answer = client.post(
        "/v1/payments",
        json={"booking_public_id": first["public_id"], "amount": 100000, "kind": "full"},
    )
    assert answer.status_code == 200, answer.text
    assert charged["amount"] == 200000


def test_a_deposit_cannot_be_more_than_the_visit_is_worth(client: TestClient, monkeypatch):
    data = _two_hour_visit(client)
    first = data["booked"]["bookings"][0]

    charged = {}

    def fake_checkout(**kwargs):
        charged["amount"] = kwargs["amount"]
        from app.services.doku import CheckoutResult

        return CheckoutResult(
            invoice_number=kwargs["invoice_number"],
            checkout_url="https://pay.test/x",
            token_id="tok",
        )

    monkeypatch.setattr(payments.doku, "create_checkout", fake_checkout)

    client.post(
        "/v1/payments",
        json={"booking_public_id": first["public_id"], "amount": 999999, "kind": "deposit"},
    )
    assert charged["amount"] == 200000


def test_paying_confirms_every_hour_of_the_visit(client: TestClient, monkeypatch):
    """No hour of a paid visit is left hanging."""
    data = _two_hour_visit(client)
    first = data["booked"]["bookings"][0]
    second = data["booked"]["bookings"][1]

    # The manager marks the invoice paid, as the gateway would.
    def fake_checkout(**kwargs):
        from app.services.doku import CheckoutResult

        return CheckoutResult(
            invoice_number=kwargs["invoice_number"],
            checkout_url="https://pay.test/x",
            token_id="tok",
        )

    monkeypatch.setattr(payments.doku, "create_checkout", fake_checkout)
    monkeypatch.setattr(payments.settings, "doku_client_id", "id")
    monkeypatch.setattr(payments.settings, "doku_secret_key", "secret")

    payment = client.post(
        "/v1/payments",
        json={"booking_public_id": first["public_id"], "amount": 200000, "kind": "full"},
    )
    assert payment.status_code == 200, payment.text

    rows = client.get(f"/v1/payments?booking_public_id={first['public_id']}").json()
    assert rows
    marked = client.post(f"/v1/payments/{rows[0]['public_id']}/mark-paid")
    assert marked.status_code == 200

    assert client.get(f"/v1/bookings/{first['public_id']}").json()["status"] == "confirmed"
    assert client.get(f"/v1/bookings/{second['public_id']}").json()["status"] == "confirmed"


def test_the_second_hour_does_not_open_a_second_invoice(client: TestClient, monkeypatch):
    """One visit, one invoice — whichever hour the page asks about."""
    data = _two_hour_visit(client)
    first = data["booked"]["bookings"][0]
    second = data["booked"]["bookings"][1]

    calls = []

    def fake_checkout(**kwargs):
        calls.append(kwargs["invoice_number"])
        from app.services.doku import CheckoutResult

        return CheckoutResult(
            invoice_number=kwargs["invoice_number"],
            checkout_url="https://pay.test/x",
            token_id="tok",
        )

    monkeypatch.setattr(payments.doku, "create_checkout", fake_checkout)

    one = client.post(
        "/v1/payments",
        json={"booking_public_id": first["public_id"], "amount": 200000, "kind": "full"},
    )
    assert one.status_code == 200, one.text

    two = client.post(
        "/v1/payments",
        json={"booking_public_id": second["public_id"], "amount": 200000, "kind": "full"},
    )
    assert two.status_code == 200, two.text

    # The same invoice comes back, and the gateway was only asked once.
    assert one.json()["invoice_number"] == two.json()["invoice_number"]
    assert len(calls) == 1


def test_both_hours_of_a_paid_visit_read_as_paid(client: TestClient, monkeypatch):
    """The second hour of a paid visit is not "unpaid"."""
    data = _two_hour_visit(client)
    first = data["booked"]["bookings"][0]
    second = data["booked"]["bookings"][1]

    def fake_checkout(**kwargs):
        from app.services.doku import CheckoutResult

        return CheckoutResult(
            invoice_number=kwargs["invoice_number"],
            checkout_url="https://pay.test/x",
            token_id="tok",
        )

    monkeypatch.setattr(payments.doku, "create_checkout", fake_checkout)
    client.post(
        "/v1/payments",
        json={"booking_public_id": first["public_id"], "amount": 200000, "kind": "full"},
    )
    rows = client.get(f"/v1/payments?booking_public_id={first['public_id']}").json()
    client.post(f"/v1/payments/{rows[0]['public_id']}/mark-paid")

    second_answer = client.get(f"/v1/bookings/{second['public_id']}").json()
    assert second_answer["payment_status"] == "paid"
    assert second_answer["payment_invoice_number"] == rows[0]["invoice_number"]
