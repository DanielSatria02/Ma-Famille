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


def _venue_and_court(client, name="C1"):
    venue = client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()
    court = client.post(
        "/v1/courts",
        json={
            "venue_public_id": venue["public_id"],
            "name": name,
            "sport": "futsal",
            "price_weekday": 100000,
            "price_weekend": 150000,
        },
    ).json()
    return venue, court


def test_generate_fills_open_hours_and_is_idempotent():
    client = _client()
    try:
        _, court = _venue_and_court(client)
        # 2026-10-19 is a Monday, 2026-10-20 a Tuesday; defaults are 08:00-22:00.
        body = {
            "court_public_id": court["public_id"],
            "from_day": "2026-10-19",
            "to_day": "2026-10-20",
        }
        first = client.post("/v1/slots/generate", json=body)
        assert first.status_code == 201, first.text
        assert first.json() == {
            "from_day": "2026-10-19",
            "to_day": "2026-10-20",
            "courts": 1,
            "created": 28,
            "skipped_existing": 0,
            "skipped_closed_days": 0,
            "skipped_unpriced": 0,
        }

        again = client.post("/v1/slots/generate", json=body).json()
        assert again["created"] == 0
        assert again["skipped_existing"] == 28

        day = client.get(
            "/v1/slots",
            params={"court_public_id": court["public_id"], "day": "2026-10-19"},
        ).json()
        assert len(day) == 14
        assert day[0]["starts_at"].startswith("2026-10-19T08:00")
        assert day[-1]["starts_at"].startswith("2026-10-19T21:00")
        assert day[-1]["ends_at"].startswith("2026-10-19T22:00")
        assert all(slot["status"] == "available" for slot in day)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_generate_follows_custom_hours_and_closed_days():
    client = _client()
    try:
        venue, court = _venue_and_court(client)
        # Monday 04:00-23:00 -> 19 hourly slots.
        client.put(
            f"/v1/venues/{venue['public_id']}/hours/0",
            json={"opens_at": "04:00", "closes_at": "23:00"},
        )
        monday = client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-19",
                "to_day": "2026-10-19",
            },
        ).json()
        assert monday["created"] == 19

        # Sunday closed -> nothing generated, day reported as skipped.
        client.put(
            f"/v1/venues/{venue['public_id']}/hours/6",
            json={"opens_at": "08:00", "closes_at": "22:00", "is_closed": True},
        )
        sunday = client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-25",
                "to_day": "2026-10-25",
            },
        ).json()
        assert sunday["created"] == 0
        assert sunday["skipped_closed_days"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_generate_prices_weekends_and_covers_venue():
    client = _client()
    try:
        venue, _ = _venue_and_court(client)
        client.post(
            "/v1/courts",
            json={
                "venue_public_id": venue["public_id"],
                "name": "C2",
                "sport": "badminton",
                "price_weekday": 50000,
                "price_weekend": 80000,
            },
        )
        created = client.post(
            "/v1/slots/generate",
            json={
                "venue_public_id": venue["public_id"],
                "from_day": "2026-10-24",
                "to_day": "2026-10-24",
            },
        ).json()
        assert created["courts"] == 2
        assert created["created"] == 28

        courts = client.get(
            "/v1/courts", params={"venue_public_id": venue["public_id"]}
        ).json()
        saturday = client.get(
            "/v1/slots", params={"court_public_id": courts[0]["public_id"], "day": "2026-10-24"}
        ).json()
        assert saturday[0]["price"] == 150000
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_generate_rejects_bad_input():
    client = _client()
    try:
        venue, court = _venue_and_court(client)
        both = client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "venue_public_id": venue["public_id"],
                "from_day": "2026-10-19",
                "to_day": "2026-10-19",
            },
        )
        assert both.status_code == 422

        neither = client.post(
            "/v1/slots/generate",
            json={"from_day": "2026-10-19", "to_day": "2026-10-19"},
        )
        assert neither.status_code == 422

        backwards = client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "from_day": "2026-10-20",
                "to_day": "2026-10-19",
            },
        )
        assert backwards.status_code == 422

        unknown = client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": "00000000-0000-0000-0000-000000000000",
                "from_day": "2026-10-19",
                "to_day": "2026-10-19",
            },
        )
        assert unknown.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
