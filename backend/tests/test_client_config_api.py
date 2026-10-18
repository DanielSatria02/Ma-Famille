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
        }
    finally:
        app.dependency_overrides.pop(get_db, None)


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
