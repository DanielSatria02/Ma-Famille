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


def _venue(client, name, address="Jakarta", **overrides):
    payload = {"name": name, "address": address}
    payload.update(overrides)
    return client.post("/v1/venues", json=payload).json()


def test_venue_tags_are_normalised_and_returned():
    client = _client()
    try:
        venue = _venue(
            client,
            "GOR Senayan",
            tags=["Outdoors", " birthdays ", "outdoors", ""],
            lat=-6.2185,
            lng=106.8022,
        )
        assert venue["tags"] == ["outdoors", "birthdays"]
        assert venue["lat"] == -6.2185
        assert venue["lng"] == 106.8022

        fetched = client.get(f"/v1/venues/{venue['public_id']}").json()
        assert fetched["tags"] == ["outdoors", "birthdays"]

        # Untagged venues stay valid.
        plain = _venue(client, "Lapangan Biasa")
        assert plain["tags"] == []
        assert plain["lat"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_venue_filters_and_tag_vocabulary():
    client = _client()
    try:
        _venue(client, "GOR Senayan", address="Jakarta Pusat", tags=["indoors"])
        _venue(client, "Padel Cinere", address="Depok", tags=["outdoors", "birthdays"])
        _venue(client, "Kopi Corner", address="Depok", tags=["indoors"])

        outdoors = client.get("/v1/venues", params={"tag": "outdoors"}).json()
        assert [venue["name"] for venue in outdoors] == ["Padel Cinere"]

        searched = client.get("/v1/venues", params={"q": "depok"}).json()
        assert sorted(venue["name"] for venue in searched) == [
            "Kopi Corner",
            "Padel Cinere",
        ]

        combined = client.get(
            "/v1/venues", params={"q": "depok", "tag": "indoors"}
        ).json()
        assert [venue["name"] for venue in combined] == ["Kopi Corner"]

        assert client.get("/v1/venues/tags").json() == [
            "birthdays",
            "indoors",
            "outdoors",
        ]

        assert client.get("/v1/venues", params={"q": "nothing here"}).json() == []
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_venue_update_handles_tags_and_coordinates():
    client = _client()
    try:
        venue = _venue(client, "GOR Senayan", tags=["indoors"])

        updated = client.patch(
            f"/v1/venues/{venue['public_id']}",
            json={"tags": ["outdoors", "event"], "lat": -6.2, "lng": 106.8},
        ).json()
        assert updated["tags"] == ["outdoors", "event"]
        assert updated["lat"] == -6.2

        # Clearing coordinates keeps the tags, and vice versa.
        cleared = client.patch(
            f"/v1/venues/{venue['public_id']}", json={"lat": None, "lng": None}
        ).json()
        assert cleared["lat"] is None
        assert cleared["tags"] == ["outdoors", "event"]

        emptied = client.patch(
            f"/v1/venues/{venue['public_id']}", json={"tags": []}
        ).json()
        assert emptied["tags"] == []
    finally:
        app.dependency_overrides.pop(get_db, None)
