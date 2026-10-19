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


def _venue(client, name="GOR Ma-Famille"):
    return client.post("/v1/venues", json={"name": name, "address": "Jkt"}).json()


def _court(client, venue, name, kind="court", prices=(100000, 150000)):
    return client.post(
        "/v1/courts",
        json={
            "venue_public_id": venue["public_id"],
            "name": name,
            "sport": "padel",
            "kind": kind,
            "price_weekday": prices[0] if prices else None,
            "price_weekend": prices[1] if prices else None,
        },
    ).json()


def test_facilities_list_marks_what_can_be_booked():
    client = _client()
    try:
        venue = _venue(client)
        bookable = _court(client, venue, "Futsal A")
        unpriced = _court(client, venue, "Kopi Corner", kind="cafe", prices=None)
        client.patch(f"/v1/courts/{unpriced['public_id']}", json={"is_active": False})

        listed = client.get("/v1/facilities").json()
        assert len(listed) == 2
        by_name = {entry["name"]: entry for entry in listed}

        assert by_name["Futsal A"]["is_bookable"] is True
        assert by_name["Futsal A"]["unavailable_reason"] is None
        assert by_name["Futsal A"]["venue"]["name"] == "GOR Ma-Famille"
        assert by_name["Futsal A"]["price_weekday"] == 100000
        assert by_name["Futsal A"]["public_id"] == bookable["public_id"]

        assert by_name["Kopi Corner"]["kind"] == "cafe"
        assert by_name["Kopi Corner"]["is_bookable"] is False
        assert by_name["Kopi Corner"]["unavailable_reason"] == "inactive"
        # Public payload stays free of manager-only flags.
        assert "locked" not in by_name["Futsal A"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_facilities_filter_by_kind_and_venue():
    client = _client()
    try:
        first = _venue(client, "GOR A")
        second = _venue(client, "GOR B")
        _court(client, first, "Futsal A")
        _court(client, first, "Kopi Corner", kind="cafe", prices=None)
        _court(client, second, "Meeting Room", kind="office")

        cafes = client.get("/v1/facilities", params={"kind": "cafe"}).json()
        assert [entry["name"] for entry in cafes] == ["Kopi Corner"]

        only_first = client.get(
            "/v1/facilities", params={"venue_public_id": first["public_id"]}
        ).json()
        assert sorted(entry["name"] for entry in only_first) == [
            "Futsal A",
            "Kopi Corner",
        ]

        assert (
            client.get(
                "/v1/facilities",
                params={"venue_public_id": "00000000-0000-0000-0000-000000000000"},
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_manager_facilities_flag_locked_until_priced():
    client = _client()
    try:
        venue = _venue(client)
        priced = _court(client, venue, "Futsal A")
        unpriced = _court(client, venue, "Badminton 1", prices=None)

        listed = client.get("/v1/manager/facilities").json()
        by_name = {entry["name"]: entry for entry in listed}
        assert by_name["Futsal A"]["locked"] is False
        assert by_name["Badminton 1"]["locked"] is True
        assert by_name["Badminton 1"]["is_price_set"] is False

        # Pricing the facility unlocks the switch straight away.
        client.patch(
            f"/v1/courts/{unpriced['public_id']}",
            json={"price_weekday": 50000, "price_weekend": 80000},
        )
        refreshed = {
            entry["name"]: entry
            for entry in client.get("/v1/manager/facilities").json()
        }
        assert refreshed["Badminton 1"]["locked"] is False
        assert refreshed["Badminton 1"]["is_bookable"] is True
        assert refreshed["Futsal A"]["public_id"] == priced["public_id"]
    finally:
        app.dependency_overrides.pop(get_db, None)
