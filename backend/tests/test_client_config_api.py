import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
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


def test_config_reports_booking_ttl_and_feature_availability(monkeypatch):
    client = _client()
    monkeypatch.setattr(settings, "booking_ttl_minutes", 45)
    monkeypatch.setattr(settings, "booking_min_lead_days", 1)
    monkeypatch.setattr(settings, "manager_password", "rahasia")
    monkeypatch.setattr(settings, "doku_client_id", "MCH-1")
    monkeypatch.setattr(settings, "doku_secret_key", "SK-1")
    try:
        body = client.get("/v1/config").json()
        assert body == {
            "booking_ttl_minutes": 45,
            "booking_min_lead_days": 1,
            "manager_login_enabled": True,
            "payment_configured": True,
            "payment_problem": "",
        }
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_config_does_not_call_a_snap_key_a_working_gateway(monkeypatch):
    """A SNAP API key is present and is still not a Secret Key.

    DOKU issues both. Filling DOKU_SECRET_KEY with the SNAP one leaves a config
    that looks complete and signs nothing the checkout endpoint accepts, so a
    client told "configured" would offer a Pay button that fails every time.
    """
    client = _client()
    monkeypatch.setattr(settings, "doku_client_id", "BRN-0260-1")
    monkeypatch.setattr(settings, "doku_secret_key", "doku_key_sandbox_abc123")
    try:
        body = client.get("/v1/config").json()
        assert body["payment_configured"] is False
        assert "SNAP" in body["payment_problem"]
        # The reason is for whoever is looking at the deploy, so it must not
        # repeat the key back at them.
        assert "abc123" not in body["payment_problem"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_checkout_refuses_before_calling_doku_with_a_snap_key(monkeypatch):
    """The gateway itself must not build a request it knows will be rejected."""
    from app.services import doku as doku_service

    monkeypatch.setattr(settings, "doku_client_id", "BRN-0260-1")
    monkeypatch.setattr(settings, "doku_secret_key", "doku_key_sandbox_abc123")

    def _boom(*args, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("DOKU was called with a key that cannot sign")

    monkeypatch.setattr(doku_service.httpx, "post", _boom)
    with pytest.raises(doku_service.DokuError, match="SNAP"):
        doku_service.create_checkout(
            invoice_number="MAF-TEST-1", amount=1000, customer_name="Test"
        )


def test_config_defaults_on_a_bare_dev_server(monkeypatch):
    """No password and no DOKU keys — the client must be able to see that."""
    client = _client()
    monkeypatch.setattr(settings, "manager_password", "")
    monkeypatch.setattr(settings, "doku_client_id", "")
    monkeypatch.setattr(settings, "doku_secret_key", "")
    try:
        body = client.get("/v1/config").json()
        assert body["manager_login_enabled"] is False
        assert body["payment_configured"] is False
        assert body["booking_ttl_minutes"] >= 1
    finally:
        app.dependency_overrides.pop(get_db, None)
