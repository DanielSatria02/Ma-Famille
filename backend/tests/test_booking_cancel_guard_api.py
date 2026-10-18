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


def _visit(client, contact="0812-3456-7890", day="2026-10-19"):
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
        json={"court_public_id": court["public_id"], "from_day": day, "to_day": day},
    )
    created = client.post(
        "/v1/bookings/range",
        json={
            "court_public_id": court["public_id"],
            "starts_at": f"{day}T09:00:00",
            "ends_at": f"{day}T11:00:00",
            "customer_name": "Budi",
            "customer_contact": contact,
        },
    ).json()
    return created


def test_contact_normalisation_handles_phone_and_text():
    from app.services.bookings import normalise_contact

    for phone in ("0812-3456-7890", "812 3456 7890", "+62 812 3456 7890", "62 81234567890"):
        assert normalise_contact(phone) == "81234567890"
    assert normalise_contact(" Budi@Example.com ") == "budi@example.com"
    assert normalise_contact("0812000000") == "812000000"


def test_a_customer_cancels_with_the_booking_contact(monkeypatch):
    client = _client()
    try:
        visit = _visit(client)
        other = _visit(client, contact="budi@example.com")
        # A manager password appears, so the routes are no longer wide open and
        # writes need a token.
        monkeypatch.setattr(settings, "manager_password", "rahasia")
        group = visit["group_public_id"]

        assert client.post(f"/v1/bookings/groups/{group}/cancel").status_code == 403
        wrong = client.post(
            f"/v1/bookings/groups/{group}/cancel", params={"customer_contact": "0899999"}
        )
        assert wrong.status_code == 403

        # Same customer, number written differently.
        ok = client.post(
            f"/v1/bookings/groups/{group}/cancel",
            params={"customer_contact": "+62 812 3456 7890"},
        )
        assert ok.status_code == 200, ok.text
        assert [b["status"] for b in ok.json()] == ["cancelled", "cancelled"]

        # Single booking route accepts the contact too.
        booking_id = other["bookings"][0]["public_id"]
        assert client.post(f"/v1/bookings/{booking_id}/cancel").status_code == 403
        allowed = client.post(
            f"/v1/bookings/{booking_id}/cancel",
            params={"customer_contact": "Budi@Example.com"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["status"] == "cancelled"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_manager_token_still_cancels_anything(monkeypatch):
    client = _client()
    try:
        visit = _visit(client)
        monkeypatch.setattr(settings, "manager_password", "rahasia")
        login = client.post("/v1/auth/login", json={"password": "rahasia"}).json()
        headers = {"X-Manager-Token": login["token"]}
        group = visit["group_public_id"]

        res = client.post(f"/v1/bookings/groups/{group}/cancel", headers=headers)
        assert res.status_code == 200
        assert all(b["status"] == "cancelled" for b in res.json())

        unknown = client.post(
            "/v1/bookings/groups/01a14d3b-969b-7084-ab09-760a34d343dc/cancel",
            headers=headers,
        )
        assert unknown.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_without_any_configuration_the_routes_stay_open(monkeypatch):
    """Local dev: no token and no password means everything is a manager."""
    client = _client()
    monkeypatch.setattr(settings, "manager_token", "")
    monkeypatch.setattr(settings, "manager_password", "")
    try:
        visit = _visit(client)
        res = client.post(f"/v1/bookings/groups/{visit['group_public_id']}/cancel")
        assert res.status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
