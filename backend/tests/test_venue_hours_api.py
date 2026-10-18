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


def _venue(client) -> str:
    return client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()[
        "public_id"
    ]


def test_hours_default_to_full_week():
    client = _client()
    try:
        hours = client.get(f"/v1/venues/{_venue(client)}/hours")
        assert hours.status_code == 200, hours.text
        days = hours.json()
        assert [day["day_of_week"] for day in days] == list(range(7))
        assert days[0]["day"] == "Monday"
        assert days[6]["day"] == "Sunday"
        assert days[0]["opens_at"] == "08:00"
        assert days[0]["closes_at"] == "22:00"
        assert all(day["is_default"] for day in days)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_hours_upsert_overrides_one_day():
    client = _client()
    try:
        venue_id = _venue(client)
        saved = client.put(
            f"/v1/venues/{venue_id}/hours/0",
            json={"opens_at": "04:00", "closes_at": "23:00"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json() == {
            "day_of_week": 0,
            "day": "Monday",
            "opens_at": "04:00",
            "closes_at": "23:00",
            "is_closed": False,
            "is_default": False,
        }

        days = client.get(f"/v1/venues/{venue_id}/hours").json()
        assert days[0]["opens_at"] == "04:00"
        assert days[0]["is_default"] is False
        # The other days keep the default window.
        assert days[1]["is_default"] is True

        # Second write for the same day updates in place instead of duplicating.
        again = client.put(
            f"/v1/venues/{venue_id}/hours/0",
            json={"opens_at": "05:00", "closes_at": "21:00"},
        )
        assert again.json()["opens_at"] == "05:00"
        assert len(client.get(f"/v1/venues/{venue_id}/hours").json()) == 7
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_hours_reject_bad_input():
    client = _client()
    try:
        venue_id = _venue(client)
        backwards = client.put(
            f"/v1/venues/{venue_id}/hours/2",
            json={"opens_at": "20:00", "closes_at": "09:00"},
        )
        assert backwards.status_code == 422

        bad_format = client.put(
            f"/v1/venues/{venue_id}/hours/2",
            json={"opens_at": "9am", "closes_at": "17:00"},
        )
        assert bad_format.status_code == 422

        out_of_range = client.put(
            f"/v1/venues/{venue_id}/hours/7",
            json={"opens_at": "09:00", "closes_at": "17:00"},
        )
        assert out_of_range.status_code == 422

        assert (
            client.get(
                "/v1/venues/00000000-0000-0000-0000-000000000000/hours"
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_closed_day_allows_any_time():
    client = _client()
    try:
        venue_id = _venue(client)
        closed = client.put(
            f"/v1/venues/{venue_id}/hours/6",
            json={"opens_at": "09:00", "closes_at": "09:00", "is_closed": True},
        )
        assert closed.status_code == 200, closed.text
        assert closed.json()["is_closed"] is True
    finally:
        app.dependency_overrides.pop(get_db, None)
