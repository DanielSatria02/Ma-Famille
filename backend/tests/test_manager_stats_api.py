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


def _court_with_week(client):
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
    # 2026-10-19 is a Monday, so the week runs 19-25 October.
    client.post(
        "/v1/slots/generate",
        json={
            "court_public_id": court["public_id"],
            "from_day": "2026-10-19",
            "to_day": "2026-10-25",
        },
    )
    return court


def _book(client, court, day, start, end):
    return client.post(
        "/v1/bookings/range",
        json={
            "court_public_id": court["public_id"],
            "starts_at": f"{day}T{start}:00",
            "ends_at": f"{day}T{end}:00",
            "customer_name": "Budi",
            "customer_contact": "0812",
        },
    ).json()


def test_stats_count_visits_not_hours():
    client = _client()
    try:
        court = _court_with_week(client)
        _book(client, court, "2026-10-19", "09", "12")  # one 3-hour visit
        _book(client, court, "2026-10-21", "14", "15")  # one 1-hour visit

        stats = client.get("/v1/manager/stats", params={"day": "2026-10-19"}).json()
        assert stats == {
            "day": "2026-10-19",
            "week_start": "2026-10-19",
            "week_end": "2026-10-25",
            "todays_bookings": 1,
            "weekly_visitors": 2,
            "cancelled_bookings": 0,
        }

        other_day = client.get("/v1/manager/stats", params={"day": "2026-10-20"}).json()
        assert other_day["todays_bookings"] == 0
        assert other_day["weekly_visitors"] == 2

        outside = client.get("/v1/manager/stats", params={"day": "2026-10-26"}).json()
        assert outside["weekly_visitors"] == 0
        assert outside["week_start"] == "2026-10-26"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_stats_count_cancelled_visits_separately():
    client = _client()
    try:
        court = _court_with_week(client)
        kept = _book(client, court, "2026-10-19", "09", "10")
        dropped = _book(client, court, "2026-10-20", "09", "11")
        client.post(f"/v1/bookings/groups/{dropped['group_public_id']}/cancel")

        stats = client.get("/v1/manager/stats", params={"day": "2026-10-19"}).json()
        assert stats["weekly_visitors"] == 1
        assert stats["todays_bookings"] == 1
        assert stats["cancelled_bookings"] == 1

        # The kept visit is still a single group.
        assert kept["hours"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_stats_accepts_explicit_week_start_and_guards_order():
    client = _client()
    try:
        _court_with_week(client)
        shifted = client.get(
            "/v1/manager/stats",
            params={"day": "2026-10-21", "week_start": "2026-10-19"},
        ).json()
        assert shifted["week_start"] == "2026-10-19"
        assert shifted["week_end"] == "2026-10-25"

        bad = client.get(
            "/v1/manager/stats",
            params={"day": "2026-10-19", "week_start": "2026-10-26"},
        )
        assert bad.status_code == 422

        # No params: defaults to the server's today.
        assert client.get("/v1/manager/stats").status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
