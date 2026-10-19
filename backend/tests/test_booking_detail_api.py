from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import payments as payment_routes
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services import doku


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


def _booked_range(client):
    venue = client.post(
        "/v1/venues", json={"name": "Ma-Famille Premiere", "address": "Jl. Demo 1"}
    ).json()
    court = client.post(
        "/v1/courts",
        json={
            "venue_public_id": venue["public_id"],
            "name": "Lapangan Padel 1",
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


def test_booking_carries_slot_court_venue_and_total():
    client = _client()
    try:
        group = _booked_range(client)
        first = group["bookings"][0]

        fetched = client.get(f"/v1/bookings/{first['public_id']}").json()
        assert fetched["venue"]["name"] == "Ma-Famille Premiere"
        assert fetched["court"]["name"] == "Lapangan Padel 1"
        assert fetched["court"]["sport"] == "padel"
        assert fetched["slot"]["starts_at"].startswith("2026-10-19T09:00")
        assert fetched["slot"]["ends_at"].startswith("2026-10-19T10:00")
        assert fetched["total"] == 100000
        assert fetched["payment_status"] == "unpaid"
        assert fetched["group_public_id"] == group["group_public_id"]

        history = client.get("/v1/bookings", params={"customer_contact": "0812"}).json()
        assert len(history) == 2
        assert all(row["court"]["name"] == "Lapangan Padel 1" for row in history)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_manager_list_is_render_ready():
    client = _client()
    try:
        _booked_range(client)
        rows = client.get("/v1/manager/bookings").json()
        assert len(rows) == 2
        # The manager dashboard cards need name, venue and clock times.
        assert {row["customer_name"] for row in rows} == {"Budi"}
        assert {row["venue"]["name"] for row in rows} == {"Ma-Famille Premiere"}
        assert [row["slot"]["starts_at"][11:16] for row in rows] == ["09:00", "10:00"]
        assert {row["total"] for row in rows} == {100000}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_booking_carries_the_payment_reference(monkeypatch):
    client = _client()
    monkeypatch.setattr(settings, "doku_client_id", "MCH-1")
    monkeypatch.setattr(settings, "doku_secret_key", "SK-1")
    monkeypatch.setattr(
        payment_routes.doku,
        "create_checkout",
        lambda **kwargs: doku.CheckoutResult(
            invoice_number=kwargs["invoice_number"],
            checkout_url="https://sandbox.doku.com/checkout/abc",
            token_id="tok",
        ),
    )
    try:
        group = _booked_range(client)
        booking_id = group["bookings"][0]["public_id"]
        assert client.get(f"/v1/bookings/{booking_id}").json()["payment_public_id"] is None

        invoice = client.post(
            "/v1/payments", json={"booking_public_id": booking_id, "amount": 100000}
        ).json()
        detail = client.get(f"/v1/bookings/{booking_id}").json()
        assert detail["payment_invoice_number"] == invoice["invoice_number"]
        assert detail["payment_status"] == "unpaid"

        # The path takes the payment public id, not the invoice number.
        wrong_id = client.post(f"/v1/payments/{invoice['invoice_number']}/mark-paid")
        assert wrong_id.status_code == 422

        payment_id = detail["payment_public_id"]
        assert client.post(f"/v1/payments/{payment_id}/mark-paid").status_code == 200

        after = client.get(f"/v1/bookings/{booking_id}").json()
        assert after["payment_status"] == "paid"
        # Marking a payment paid confirms the booking it belongs to.
        assert after["status"] == "confirmed"
    finally:
        app.dependency_overrides.pop(get_db, None)
