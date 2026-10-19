from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services import photos as photo_service

# A 1x1 PNG and a 1x1 JPEG, enough for the magic-byte check.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")
NOT_AN_IMAGE = b"just a text file, definitely not a photo"


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


@pytest.fixture(autouse=True)
def clean_media():
    """Uploads are written for real: leave the tree as we found it."""
    yield
    for kind in ("venues", "courts"):
        for path in (Path(settings.media_root) / kind).glob("*"):
            path.unlink()


def _venue(client, **extra):
    body = {"name": "GOR", "address": "Jl. Merdeka 1"}
    body.update(extra)
    return client.post("/v1/venues", json=body).json()


def _court(client, venue, **extra):
    body = {
        "venue_public_id": venue["public_id"],
        "name": "Lapangan Padel 1",
        "sport": "padel",
        "price_weekday": 100000,
        "price_weekend": 150000,
    }
    body.update(extra)
    return client.post("/v1/courts", json=body).json()


def test_a_venue_starts_without_a_photo_and_says_so():
    client = _client()
    try:
        venue = _venue(client)
        assert venue["image_url"] is None
        assert client.get(f"/v1/venues/{venue['public_id']}").json()["image_url"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_uploading_a_photo_stores_it_and_serves_it():
    client = _client()
    try:
        venue = _venue(client)
        res = client.put(
            f"/v1/venues/{venue['public_id']}/photo",
            content=PNG,
            headers={"Content-Type": "image/png"},
        )
        assert res.status_code == 200
        url = res.json()["image_url"]
        assert url == f"/media/venues/{venue['public_id']}.png"

        # The bytes are on disk and the app serves them back.
        stored = Path(settings.media_root) / "venues" / f"{venue['public_id']}.png"
        assert stored.read_bytes() == PNG
        served = client.get(url)
        assert served.status_code == 200
        assert served.content == PNG

        # And the row remembers the URL, in the list too.
        assert client.get(f"/v1/venues/{venue['public_id']}").json()["image_url"] == url
        listed = [
            v
            for v in client.get("/v1/venues").json()
            if v["public_id"] == venue["public_id"]
        ]
        assert listed[0]["image_url"] == url
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_second_upload_replaces_the_first_one():
    client = _client()
    try:
        venue = _venue(client)
        first = client.put(f"/v1/venues/{venue['public_id']}/photo", content=PNG).json()
        second = client.put(f"/v1/venues/{venue['public_id']}/photo", content=JPEG).json()

        assert first["image_url"].endswith(".png")
        assert second["image_url"].endswith(".jpg")
        assert client.get(first["image_url"]).status_code == 404  # the old one is gone
        assert client.get(second["image_url"]).status_code == 200
        files = list((Path(settings.media_root) / "venues").glob(f"{venue['public_id']}.*"))
        assert [f.suffix for f in files] == [".jpg"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_junk_and_oversized_uploads_are_refused():
    client = _client()
    try:
        venue = _venue(client)
        junk = client.put(f"/v1/venues/{venue['public_id']}/photo", content=NOT_AN_IMAGE)
        assert junk.status_code == 415
        assert "PNG, JPEG, GIF or WebP" in junk.json()["detail"]

        empty = client.put(f"/v1/venues/{venue['public_id']}/photo", content=b"")
        assert empty.status_code == 415
        assert empty.json()["detail"] == "the upload is empty"

        big = client.put(
            f"/v1/venues/{venue['public_id']}/photo",
            content=PNG + b"\x00" * (settings.max_photo_bytes + 1),
        )
        assert big.status_code == 413
        assert "larger than 500 kB" in big.json()["detail"]

        # Nothing was written and the row stays photoless.
        assert client.get(f"/v1/venues/{venue['public_id']}").json()["image_url"] is None
        assert list((Path(settings.media_root) / "venues").glob(f"{venue['public_id']}.*")) == []
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_removing_a_photo_deletes_the_file():
    client = _client()
    try:
        venue = _venue(client)
        url = client.put(f"/v1/venues/{venue['public_id']}/photo", content=PNG).json()["image_url"]
        assert client.delete(f"/v1/venues/{venue['public_id']}/photo").status_code == 204
        assert client.get(f"/v1/venues/{venue['public_id']}").json()["image_url"] is None
        assert client.get(url).status_code == 404
        # Removing twice is still a no-op, not an error.
        assert client.delete(f"/v1/venues/{venue['public_id']}/photo").status_code == 204
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_court_has_its_own_photo():
    client = _client()
    try:
        venue = _venue(client)
        court = _court(client, venue)
        assert court["image_url"] is None

        res = client.put(f"/v1/courts/{court['public_id']}/photo", content=PNG)
        assert res.status_code == 200
        assert res.json()["image_url"] == f"/media/courts/{court['public_id']}.png"
        assert client.get(f"/v1/courts/{court['public_id']}").json()["image_url"] == res.json()[
            "image_url"
        ]
        assert client.delete(f"/v1/courts/{court['public_id']}/photo").status_code == 204
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_unknown_rows_answer_404():
    client = _client()
    try:
        missing = "00000000-0000-7000-8000-000000000000"
        assert client.put(f"/v1/venues/{missing}/photo", content=PNG).status_code == 404
        assert client.delete(f"/v1/venues/{missing}/photo").status_code == 404
        assert client.put(f"/v1/courts/{missing}/photo", content=PNG).status_code == 404
        assert client.delete(f"/v1/courts/{missing}/photo").status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_manager_can_paste_a_link_instead():
    client = _client()
    try:
        venue = _venue(client)
        res = client.patch(
            f"/v1/venues/{venue['public_id']}",
            json={"image_url": "https://example.com/court.jpg"},
        )
        assert res.status_code == 200
        assert res.json()["image_url"] == "https://example.com/court.jpg"

        # Blank clears it; a relative path that is not an upload is refused.
        assert (
            client.patch(f"/v1/venues/{venue['public_id']}", json={"image_url": "   "})
            .json()["image_url"]
            is None
        )
        bad = client.patch(
            f"/v1/venues/{venue['public_id']}", json={"image_url": "court.jpg"}
        )
        assert bad.status_code == 422
        assert "http(s) link" in bad.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_only_png_jpeg_gif_webp_are_recognised():
    assert photo_service.sniff(PNG) == "png"
    assert photo_service.sniff(JPEG) == "jpg"
    assert photo_service.sniff(b"GIF89a\x01\x00") == "gif"
    assert photo_service.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert photo_service.sniff(NOT_AN_IMAGE) is None
    assert photo_service.sniff(b"") is None


def test_path_of_only_resolves_our_own_urls():
    assert photo_service.path_of("/media/venues/x.png") is not None
    assert photo_service.path_of("https://example.com/x.png") is None
    assert photo_service.path_of("") is None
    assert photo_service.path_of("/media/../../etc/passwd") is None
