"""The dashboard counts the day the venue is on, not the server's day.

The server runs on UTC. Between seven in the evening and midnight it was
still yesterday in Jakarta, and the manager dashboard counted the wrong
day — the counters did not match the bookings on screen.
"""

from datetime import date

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


def test_the_counters_use_the_venue_day(monkeypatch):
    client = _client()
    try:
        monkeypatch.setattr(
            type(settings), "venue_today", property(lambda self: date(2026, 10, 22))
        )
        stats = client.get("/v1/manager/stats").json()
        assert stats["day"] == "2026-10-22"
        # The week runs Monday to Sunday around that day.
        assert stats["week_start"] == "2026-10-19"
        assert stats["week_end"] == "2026-10-25"
    finally:
        app.dependency_overrides.clear()


def test_an_explicit_day_is_still_honoured(monkeypatch):
    client = _client()
    try:
        monkeypatch.setattr(
            type(settings), "venue_today", property(lambda self: date(2026, 10, 22))
        )
        stats = client.get("/v1/manager/stats", params={"day": "2026-10-01"}).json()
        assert stats["day"] == "2026-10-01"
    finally:
        app.dependency_overrides.clear()
