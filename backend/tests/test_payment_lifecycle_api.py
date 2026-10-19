from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import payments as payments_api
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.booking import Booking
from app.services import doku
from app.services import payments as payment_service
from app.services.doku import CheckoutResult, RefundResult

DAY = "2026-10-19"


def _session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _client(TestingSession):
    def override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def _booked(client, contact="0812-3456-7890"):
    venue = client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()
    court = client.post(
        "/v1/courts",
        json={
            "venue_public_id": venue["public_id"],
            "name": "Futsal A",
            "sport": "padel",
            "price_weekday": 100000,
            "price_weekend": 150000,
        },
    ).json()
    client.post(
        "/v1/slots/generate",
        json={"court_public_id": court["public_id"], "from_day": DAY, "to_day": DAY},
    )
    slot = client.get(
        "/v1/slots", params={"court_public_id": court["public_id"], "day": DAY}
    ).json()[0]
    return client.post(
        "/v1/bookings",
        json={
            "slot_public_id": slot["public_id"],
            "customer_name": "Budi",
            "customer_contact": contact,
        },
    ).json()


def _checkout(client, booking, amount=100000, request_id="req-1"):
    """Create a payment row with the gateway mocked out (works without keys)."""
    with (
        patch.object(payments_api.doku, "new_invoice_number", return_value="MAF-TEST-1"),
        patch.object(
            payments_api.doku,
            "create_checkout",
            return_value=CheckoutResult(
                invoice_number="MAF-TEST-1",
                checkout_url="https://sandbox.doku.com/checkout/x",
                token_id="tok",
                request_id=request_id,
            ),
        ),
    ):
        return client.post(
            "/v1/payments",
            json={
                "booking_public_id": booking["public_id"],
                "amount": amount,
                "kind": "deposit",
            },
        )


def _payments_of(client, booking):
    return client.get(
        "/v1/payments", params={"booking_public_id": booking["public_id"]}
    ).json()


def test_the_checkout_request_id_is_kept_for_a_later_refund(monkeypatch):
    TestingSession = _session_factory()
    client = _client(TestingSession)
    try:
        monkeypatch.setattr(settings, "doku_client_id", "MCH-1")
        monkeypatch.setattr(settings, "doku_secret_key", "secret")
        booking = _booked(client)
        assert _checkout(client, booking, request_id="req-42").status_code == 200

        payment = _payments_of(client, booking)[0]
        assert payment["invoice_number"] == "MAF-TEST-1"
        assert payment["status"] == "unpaid"

        with TestingSession() as db:
            row = payment_service.get_by_invoice(db, "MAF-TEST-1")
            assert row.provider_request_id == "req-42"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_refund_without_keys_books_it_and_says_so(monkeypatch):
    client = _client(_session_factory())
    try:
        monkeypatch.setattr(settings, "doku_client_id", "")
        monkeypatch.setattr(settings, "doku_secret_key", "")
        booking = _booked(client)
        assert _checkout(client, booking).status_code == 200
        payment = _payments_of(client, booking)[0]
        assert client.post(f"/v1/payments/{payment['public_id']}/mark-paid").status_code == 200

        res = client.post(f"/v1/payments/{payment['public_id']}/refund")
        assert res.status_code == 200
        body = res.json()
        assert body["provider"] == "local"
        assert "no DOKU keys configured" in body["detail"]
        assert body["payment"]["status"] == "refunded"
        assert body["payment"]["refunded_at"] is not None

        again = client.post(f"/v1/payments/{payment['public_id']}/refund")
        assert again.status_code == 409
        assert "refunded payment cannot be refunded" in again.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_an_unpaid_payment_cannot_be_refunded():
    client = _client(_session_factory())
    try:
        booking = _booked(client)
        _checkout(client, booking)
        payment = _payments_of(client, booking)[0]
        res = client.post(f"/v1/payments/{payment['public_id']}/refund")
        assert res.status_code == 409
        assert res.json()["detail"] == "a unpaid payment cannot be refunded"
        missing = client.post("/v1/payments/00000000-0000-7000-8000-000000000000/refund")
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_keyed_refund_goes_to_doku_and_quotes_the_request_id(monkeypatch):
    client = _client(_session_factory())
    try:
        monkeypatch.setattr(settings, "doku_client_id", "MCH-1")
        monkeypatch.setattr(settings, "doku_secret_key", "secret")
        booking = _booked(client)
        _checkout(client, booking, request_id="req-42")
        payment = _payments_of(client, booking)[0]
        client.post(f"/v1/payments/{payment['public_id']}/mark-paid")

        with patch.object(
            doku,
            "request_refund",
            return_value=RefundResult(
                status="SUCCESS", kind="FULL_REFUND", message="refunded", approval_code="A1"
            ),
        ) as sender:
            res = client.post(f"/v1/payments/{payment['public_id']}/refund")

        assert res.status_code == 200
        assert sender.call_args.kwargs == {
            "invoice_number": "MAF-TEST-1",
            "original_request_id": "req-42",
            "amount": 100000,
        }
        body = res.json()
        assert body["provider"] == "doku"
        assert body["payment"]["status"] == "refunded"
        assert body["payment"]["failure_reason"] == "FULL_REFUND A1"
        assert body["provider_status"] == "REFUNDED"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_refused_refund_leaves_the_payment_paid(monkeypatch):
    client = _client(_session_factory())
    try:
        monkeypatch.setattr(settings, "doku_client_id", "MCH-1")
        monkeypatch.setattr(settings, "doku_secret_key", "secret")
        booking = _booked(client)
        _checkout(client, booking)
        payment = _payments_of(client, booking)[0]
        client.post(f"/v1/payments/{payment['public_id']}/mark-paid")

        with patch.object(
            doku,
            "request_refund",
            side_effect=doku.DokuError("DOKU rejected the refund: HTTP 400"),
        ):
            res = client.post(f"/v1/payments/{payment['public_id']}/refund")
        assert res.status_code == 502
        assert "HTTP 400" in res.json()["detail"]
        assert _payments_of(client, booking)[0]["status"] == "paid"

        with patch.object(
            doku,
            "request_refund",
            return_value=RefundResult(status="FAILED", kind="", message="insufficient funds"),
        ):
            res = client.post(f"/v1/payments/{payment['public_id']}/refund")
        assert res.status_code == 502
        assert res.json()["detail"] == "DOKU refused the refund (FAILED): insufficient funds"
        assert _payments_of(client, booking)[0]["status"] == "paid"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_the_webhook_records_a_failure_instead_of_dropping_it(monkeypatch):
    TestingSession = _session_factory()
    client = _client(TestingSession)
    try:
        monkeypatch.setattr(settings, "doku_client_id", "MCH-1")
        monkeypatch.setattr(settings, "doku_secret_key", "secret")
        booking = _booked(client)
        _checkout(client, booking, request_id="req-42")

        monkeypatch.setattr(payments_api.doku, "verify_signature", lambda **kwargs: True)
        res = client.post(
            "/v1/payments/webhook/doku",
            json={
                "order": {"invoice_number": "MAF-TEST-1"},
                "transaction": {"status": "EXPIRED"},
            },
        )
        assert res.status_code == 200
        assert res.json()["payment_status"] == "failed"

        row = _payments_of(client, booking)[0]
        assert row["status"] == "failed"
        assert row["provider_status"] == "EXPIRED"
        assert row["failure_reason"] == "gateway reported EXPIRED"

        # A stale failure cannot wipe out a refund that happened later.
        with TestingSession() as db:
            payment = payment_service.get_by_invoice(db, "MAF-TEST-1")
            payment_service.mark_paid(db, payment)
            payment_service.mark_refunded(db, payment)
            payment_service.mark_failed(db, payment, "gateway reported EXPIRED")
            assert payment.status == "refunded"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_money_arriving_for_a_cancelled_visit_asks_for_a_refund(monkeypatch):
    client = _client(_session_factory())
    try:
        monkeypatch.setattr(settings, "doku_client_id", "MCH-1")
        monkeypatch.setattr(settings, "doku_secret_key", "secret")
        booking = _booked(client)
        _checkout(client, booking)
        client.post(f"/v1/bookings/{booking['public_id']}/cancel")

        monkeypatch.setattr(payments_api.doku, "verify_signature", lambda **kwargs: True)
        res = client.post(
            "/v1/payments/webhook/doku",
            json={
                "order": {"invoice_number": "MAF-TEST-1"},
                "transaction": {"status": "SUCCESS"},
            },
        )
        body = res.json()
        assert body["payment_status"] == "paid"
        assert body["detail"] == "paid after the visit was cancelled: a refund is needed"

        row = _payments_of(client, booking)[0]
        assert row["status"] == "paid"
        assert row["failure_reason"] == "paid after the visit was cancelled — refund it"
        # The visit stays cancelled: only the money moved.
        assert client.get(f"/v1/bookings/{booking['public_id']}").json()["status"] == "cancelled"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_the_dashboard_row_carries_the_reason(monkeypatch):
    """The manager list is built from BookingResponse: the note has to be in the schema."""
    client = _client(_session_factory())
    try:
        booking = _booked(client)
        _checkout(client, booking)
        payment = _payments_of(client, booking)[0]
        client.post(f"/v1/payments/{payment['public_id']}/mark-paid")
        client.post(f"/v1/payments/{payment['public_id']}/refund")

        row = client.get("/v1/manager/bookings", params={"day": DAY}).json()[0]
        assert row["payment_status"] == "refunded"
        assert row["payment_failure_reason"].startswith("refunded without a gateway")
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_an_expired_hold_takes_its_unpaid_invoice_with_it(monkeypatch):
    TestingSession = _session_factory()
    client = _client(TestingSession)
    try:
        booking = _booked(client)
        _checkout(client, booking)
        assert _payments_of(client, booking)[0]["status"] == "unpaid"

        with TestingSession() as db:
            row = db.scalars(
                select(Booking).where(Booking.public_id == UUID(booking["public_id"]))
            ).first()
            row.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
            db.commit()

        assert client.get(f"/v1/bookings/{booking['public_id']}").json()["status"] == "cancelled"
        row = _payments_of(client, booking)[0]
        assert row["status"] == "failed"
        assert row["failure_reason"] == "the hold expired before the payment arrived"
    finally:
        app.dependency_overrides.pop(get_db, None)
