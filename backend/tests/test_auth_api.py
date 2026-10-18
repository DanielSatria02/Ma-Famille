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


def test_login_is_disabled_until_a_password_is_configured():
    client = _client()
    try:
        res = client.post("/v1/auth/login", json={"password": "whatever"})
        assert res.status_code == 501
        assert res.json()["detail"] == "manager login is not configured"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_login_issues_a_token_that_unlocks_manager_routes(monkeypatch):
    client = _client()
    monkeypatch.setattr(settings, "manager_password", "rapat-rahasia")
    try:
        wrong = client.post("/v1/auth/login", json={"password": "salah"})
        assert wrong.status_code == 401
        assert wrong.json()["detail"] == "wrong password"

        # Manager routes are closed as soon as a password exists.
        assert client.get("/v1/manager/bookings").status_code == 401

        login = client.post(
            "/v1/auth/login",
            json={"email": "manajer@ma-famille.test", "password": "rapat-rahasia"},
        )
        assert login.status_code == 200, login.text
        body = login.json()
        assert body["role"] == "manager"
        assert body["token_type"] == "manager"
        assert body["expires_at"]

        headers = {"X-Manager-Token": body["token"]}
        assert client.get("/v1/manager/bookings", headers=headers).status_code == 200
        created = client.post(
            "/v1/venues", json={"name": "GOR", "address": "Jkt"}, headers=headers
        )
        assert created.status_code == 201

        # A garbage or tampered token stays out.
        assert (
            client.get(
                "/v1/manager/bookings", headers={"X-Manager-Token": "not-a-token"}
            ).status_code
            == 401
        )
        tampered = body["token"][:-2] + "ab"
        assert (
            client.get(
                "/v1/manager/bookings", headers={"X-Manager-Token": tampered}
            ).status_code
            == 401
        )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_expired_session_token_is_rejected(monkeypatch):
    client = _client()
    monkeypatch.setattr(settings, "manager_password", "rapat-rahasia")
    monkeypatch.setattr(settings, "manager_session_minutes", -1)
    try:
        token = client.post("/v1/auth/login", json={"password": "rapat-rahasia"}).json()
        res = client.get(
            "/v1/manager/bookings", headers={"X-Manager-Token": token["token"]}
        )
        assert res.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_cancelling_a_booking_requires_a_manager(monkeypatch):
    client = _client()
    try:
        venue = client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()
        court = client.post(
            "/v1/courts",
            json={
                "venue_public_id": venue["public_id"],
                "name": "C1",
                "sport": "futsal",
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
        booked = client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": court["public_id"],
                "starts_at": "2026-10-19T09:00:00",
                "ends_at": "2026-10-19T10:00:00",
                "customer_name": "Budi",
                "customer_contact": "0812",
            },
        ).json()
        booking_id = booked["bookings"][0]["public_id"]

        monkeypatch.setattr(settings, "manager_password", "rapat-rahasia")
        assert client.post(f"/v1/bookings/{booking_id}/cancel").status_code == 401

        token = client.post(
            "/v1/auth/login", json={"password": "rapat-rahasia"}
        ).json()["token"]
        allowed = client.post(
            f"/v1/bookings/{booking_id}/cancel", headers={"X-Manager-Token": token}
        )
        assert allowed.status_code == 200
        assert allowed.json()["status"] == "cancelled"
    finally:
        app.dependency_overrides.pop(get_db, None)
