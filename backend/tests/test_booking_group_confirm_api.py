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


def _visit(client):
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


def test_confirming_a_visit_confirms_every_hour():
    client = _client()
    try:
        visit = _visit(client)
        group = visit["group_public_id"]
        assert [b["status"] for b in visit["bookings"]] == ["pending", "pending"]

        res = client.post(f"/v1/bookings/groups/{group}/confirm")
        assert res.status_code == 200, res.text
        body = res.json()
        assert [b["status"] for b in body] == ["confirmed", "confirmed"]
        assert {b["group_public_id"] for b in body} == {group}

        # Idempotent: confirming again keeps them confirmed.
        again = client.post(f"/v1/bookings/groups/{group}/confirm")
        assert again.status_code == 200
        assert all(b["status"] == "confirmed" for b in again.json())
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_confirming_an_unknown_or_cancelled_visit():
    client = _client()
    try:
        missing = client.post(
            "/v1/bookings/groups/01a14d3b-969b-7084-ab09-760a34d343dc/confirm"
        )
        assert missing.status_code == 404

        visit = _visit(client)
        group = visit["group_public_id"]
        client.post(f"/v1/bookings/groups/{group}/cancel")

        cancelled = client.post(f"/v1/bookings/groups/{group}/confirm")
        assert cancelled.status_code == 409
        assert cancelled.json()["detail"] == "booking group is cancelled"
    finally:
        app.dependency_overrides.pop(get_db, None)
