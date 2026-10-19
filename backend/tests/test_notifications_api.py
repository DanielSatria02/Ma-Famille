from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services import notifications as notification_service

DAY = "2026-10-19"


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


def _visit(client, contact="0812-3456-7890"):
    venue = client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()
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
        json={"court_public_id": court["public_id"], "from_day": DAY, "to_day": DAY},
    )
    return client.post(
        "/v1/bookings/range",
        json={
            "court_public_id": court["public_id"],
            "starts_at": f"{DAY}T09:00:00",
            "ends_at": f"{DAY}T11:00:00",
            "customer_name": "Budi",
            "customer_contact": contact,
        },
    ).json()


def test_a_booking_queues_one_message_for_the_visit():
    client = _client()
    try:
        visit = _visit(client)
        outbox = client.get("/v1/manager/notifications").json()
        assert len(outbox) == 1

        message = outbox[0]
        assert message["event"] == "pending"
        assert message["channel"] == "whatsapp"  # a phone, not an email
        assert message["recipient"] == "0812-3456-7890"
        assert message["status"] == "queued"
        assert message["attempts"] == 0
        assert message["subject"].startswith("Booking received: Lapangan Padel 1 at GOR")
        assert "Mon 19 Oct 2026 09:00-11:00 (2 hours)" in message["body"]
        assert "Total: 200000" in message["body"]
        assert "Hi Budi" in message["body"]

        # Confirming and cancelling both add a message, not replace one.
        client.post(f"/v1/bookings/groups/{visit['group_public_id']}/confirm")
        client.post(f"/v1/bookings/groups/{visit['group_public_id']}/cancel")
        events = [row["event"] for row in client.get("/v1/manager/notifications").json()]
        assert events == ["cancelled", "confirmed", "pending"]

        assert client.get("/v1/manager/notifications", params={"status": "queued"}).json()[
            0
        ]["event"] == "cancelled"
        assert client.get("/v1/manager/notifications", params={"status": "sent"}).json() == []
        assert (
            client.get("/v1/manager/notifications", params={"status": "nonsense"}).status_code
            == 422
        )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_an_email_contact_gets_an_email_message():
    client = _client()
    try:
        _visit(client, contact="budi@example.com")
        message = client.get("/v1/manager/notifications").json()[0]
        assert message["channel"] == "email"
        assert message["recipient"] == "budi@example.com"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_dispatching_without_a_provider_logs_instead_of_pretending(monkeypatch):
    client = _client()
    try:
        _visit(client)
        monkeypatch.setattr(settings, "notify_transport", "log")

        result = client.post("/v1/manager/notifications/dispatch").json()
        assert result == {
            "transport": "log",
            "sent": 0,
            "logged": 1,
            "failed": 0,
            "still_queued": 0,
        }

        message = client.get("/v1/manager/notifications").json()[0]
        assert message["status"] == "logged"
        assert message["transport"] == "log"
        assert message["attempts"] == 1
        assert message["sent_at"] is not None
        # A second pass has nothing left to do.
        assert client.post("/v1/manager/notifications/dispatch").json()["logged"] == 0
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_an_unconfigured_smtp_keeps_the_message_queued(monkeypatch):
    client = _client()
    try:
        _visit(client, contact="budi@example.com")
        monkeypatch.setattr(settings, "notify_transport", "smtp")
        monkeypatch.setattr(settings, "smtp_host", "")

        result = client.post("/v1/manager/notifications/dispatch").json()
        assert result["sent"] == 0
        assert result["still_queued"] == 1

        message = client.get("/v1/manager/notifications").json()[0]
        assert message["status"] == "queued"
        assert message["error"] == "SMTP_HOST is not set"
        assert message["attempts"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_smtp_sends_and_reports_the_transport(monkeypatch):
    client = _client()
    try:
        _visit(client, contact="budi@example.com")
        monkeypatch.setattr(settings, "notify_transport", "smtp")
        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")

        with patch.object(notification_service, "_send_email") as sender:
            result = client.post("/v1/manager/notifications/dispatch").json()
        assert sender.call_count == 1
        assert result["sent"] == 1

        message = client.get("/v1/manager/notifications").json()[0]
        assert message["status"] == "sent"
        assert message["transport"] == "smtp"
        assert message["error"] == ""
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_provider_error_is_kept_on_the_row(monkeypatch):
    client = _client()
    try:
        _visit(client, contact="budi@example.com")
        monkeypatch.setattr(settings, "notify_transport", "smtp")
        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")

        with patch.object(
            notification_service, "_send_email", side_effect=RuntimeError("mailbox full")
        ):
            result = client.post("/v1/manager/notifications/dispatch").json()
        assert result["failed"] == 1
        assert result["sent"] == 0

        message = client.get("/v1/manager/notifications").json()[0]
        assert message["status"] == "failed"
        assert message["error"] == "mailbox full"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_whatsapp_number_normalisation():
    assert notification_service.whatsapp_number("0812-3456-7890") == "6281234567890"
    assert notification_service.whatsapp_number("+62 812 3456 7890") == "6281234567890"
    assert notification_service.whatsapp_number("81234567890") == "6281234567890"
    assert notification_service.channel_for("budi@example.com") == "email"
    assert notification_service.channel_for("081234567890") == "whatsapp"
