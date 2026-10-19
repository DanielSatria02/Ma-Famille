from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

DAY = "2026-10-19"


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


def _venue_with_courts(client, names=("C1",)):
    venue = client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()
    courts = []
    for name in names:
        courts.append(
            client.post(
                "/v1/courts",
                json={
                    "venue_public_id": venue["public_id"],
                    "name": name,
                    "sport": "padel",
                    "price_weekday": 100000,
                    "price_weekend": 150000,
                },
            ).json()
        )
    return venue, courts


def _slots(client, court):
    return client.get(
        "/v1/slots", params={"court_public_id": court["public_id"], "day": DAY}
    ).json()


def test_closing_a_window_blocks_only_that_window():
    client = _client()
    try:
        _, (court,) = _venue_with_courts(client)
        client.post(
            "/v1/slots/generate",
            json={"court_public_id": court["public_id"], "from_day": DAY, "to_day": DAY},
        )

        res = client.post(
            "/v1/slots/block",
            json={
                "court_public_id": court["public_id"],
                "from_day": DAY,
                "to_day": DAY,
                "from_hour": 9,
                "to_hour": 12,
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["updated"] == 3
        assert body["status"] == "blocked"
        assert body["courts"] == 1 and body["days"] == 1

        by_hour = {slot["starts_at"][11:13]: slot["status"] for slot in _slots(client, court)}
        assert [by_hour[str(hour).zfill(2)] for hour in (8, 9, 10, 11, 12)] == [
            "available",
            "blocked",
            "blocked",
            "blocked",
            "available",
        ]

        # Reopening puts the hours back on sale, price untouched.
        reopen = client.post(
            "/v1/slots/block",
            json={
                "court_public_id": court["public_id"],
                "from_day": DAY,
                "to_day": DAY,
                "from_hour": 9,
                "to_hour": 12,
                "status": "available",
            },
        )
        assert reopen.status_code == 200
        assert reopen.json()["updated"] == 3
        assert {slot["status"] for slot in _slots(client, court)} == {"available"}
        assert {slot["price"] for slot in _slots(client, court)} == {100000}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_booked_hour_is_never_closed():
    client = _client()
    try:
        _, (court,) = _venue_with_courts(client)
        client.post(
            "/v1/slots/generate",
            json={"court_public_id": court["public_id"], "from_day": DAY, "to_day": DAY},
        )
        booked = client.post(
            "/v1/bookings",
            json={
                "slot_public_id": next(
                    slot["public_id"]
                    for slot in _slots(client, court)
                    if slot["starts_at"][11:13] == "10"
                ),
                "customer_name": "Budi",
                "customer_contact": "0812",
            },
        )
        assert booked.status_code == 201, booked.text

        res = client.post(
            "/v1/slots/block",
            json={
                "court_public_id": court["public_id"],
                "from_day": DAY,
                "to_day": DAY,
                "from_hour": 9,
                "to_hour": 12,
            },
        )
        body = res.json()
        assert body["updated"] == 2
        assert body["skipped_booked"] == 1

        by_hour = {slot["starts_at"][11:13]: slot["status"] for slot in _slots(client, court)}
        assert by_hour["10"] == "booked"
        assert by_hour["09"] == "blocked" and by_hour["11"] == "blocked"

        # Nor is a booked hour opened up again by "reopen".
        reopen = client.post(
            "/v1/slots/block",
            json={
                "court_public_id": court["public_id"],
                "from_day": DAY,
                "to_day": DAY,
                "from_hour": 10,
                "to_hour": 11,
                "status": "available",
            },
        )
        assert reopen.json() == {
            "from_day": DAY,
            "to_day": DAY,
            "from_hour": 10,
            "to_hour": 11,
            "status": "available",
            "courts": 1,
            "days": 1,
            "updated": 0,
            "unchanged": 0,
            "skipped_booked": 1,
            "skipped_missing": 0,
        }
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_venue_wide_window_hits_every_court():
    client = _client()
    try:
        venue, courts = _venue_with_courts(client, names=("C1", "C2"))
        for court in courts:
            client.post(
                "/v1/slots/generate",
                json={"court_public_id": court["public_id"], "from_day": DAY, "to_day": DAY},
            )

        res = client.post(
            "/v1/slots/block",
            json={
                "venue_public_id": venue["public_id"],
                "from_day": DAY,
                "to_day": DAY,
                "from_hour": 8,
                "to_hour": 10,
            },
        )
        body = res.json()
        assert body["courts"] == 2
        assert body["updated"] == 4
        for court in courts:
            blocked = [
                slot
                for slot in _slots(client, court)
                if slot["status"] == "blocked"
            ]
            assert len(blocked) == 2
            assert {slot["starts_at"][11:13] for slot in blocked} == {"08", "09"}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_hours_without_a_slot_row_are_reported_not_created():
    client = _client()
    try:
        _, (court,) = _venue_with_courts(client)
        # No slots generated at all: nothing to close.
        res = client.post(
            "/v1/slots/block",
            json={
                "court_public_id": court["public_id"],
                "from_day": DAY,
                "to_day": DAY,
                "from_hour": 9,
                "to_hour": 11,
            },
        )
        assert res.status_code == 200
        assert res.json()["skipped_missing"] == 2
        assert res.json()["updated"] == 0
        assert _slots(client, court) == []
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_bad_windows_and_unknown_targets():
    client = _client()
    try:
        venue, (court,) = _venue_with_courts(client)
        base = {
            "court_public_id": court["public_id"],
            "from_day": DAY,
            "to_day": DAY,
            "from_hour": 9,
            "to_hour": 11,
        }

        assert (
            client.post(
                "/v1/slots/block", json=base | {"court_public_id": None}
            ).status_code
            == 422
        )
        # Both targets at once is ambiguous.
        assert (
            client.post(
                "/v1/slots/block", json=base | {"venue_public_id": venue["public_id"]}
            ).status_code
            == 422
        )
        # The venue itself is unknown.
        assert (
            client.post(
                "/v1/slots/block",
                json=base
                | {
                    "venue_public_id": "01a14d3b-969b-7084-ab09-760a34d343dc",
                    "court_public_id": None,
                },
            ).status_code
            == 404
        )
        assert (
            client.post("/v1/slots/block", json=base | {"to_hour": 9}).status_code == 422
        )
        assert (
            client.post("/v1/slots/block", json=base | {"to_day": "2026-10-18"}).status_code
            == 422
        )
        assert (
            client.post("/v1/slots/block", json=base | {"to_day": "2027-01-01"}).status_code == 422
        )
        assert (
            client.post(
                "/v1/slots/block",
                json=base | {"court_public_id": "01a14d3b-969b-7084-ab09-760a34d343dc"},
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
