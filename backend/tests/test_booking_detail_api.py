from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


def _booked_range(client):
    venue = client.post(
        "/v1/venues", json={"name": "GOR Ma-Famille", "address": "Jl. Demo 1"}
    ).json()
    court = client.post(
        "/v1/courts",
        json={
            "venue_public_id": venue["public_id"],
            "name": "Futsal A",
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
        assert fetched["venue"]["name"] == "GOR Ma-Famille"
        assert fetched["court"]["name"] == "Futsal A"
        assert fetched["court"]["sport"] == "futsal"
        assert fetched["slot"]["starts_at"].startswith("2026-10-19T09:00")
        assert fetched["slot"]["ends_at"].startswith("2026-10-19T10:00")
        assert fetched["total"] == 100000
        assert fetched["payment_status"] == "unpaid"
        assert fetched["group_public_id"] == group["group_public_id"]

        history = client.get("/v1/bookings", params={"customer_contact": "0812"}).json()
        assert len(history) == 2
        assert all(row["court"]["name"] == "Futsal A" for row in history)
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
        assert {row["venue"]["name"] for row in rows} == {"GOR Ma-Famille"}
        assert [row["slot"]["starts_at"][11:16] for row in rows] == ["09:00", "10:00"]
        assert {row["total"] for row in rows} == {100000}
    finally:
        app.dependency_overrides.pop(get_db, None)
