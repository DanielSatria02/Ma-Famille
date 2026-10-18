"""Peak-hour pricing: a premium rate for a window of hours, layered over the
day's weekday/weekend rate. Active only when price + start + end are all set.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Monday 2026-10-19, a weekday, so weekday rate applies outside peak.
WEEKDAY = "2026-10-19"


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


def _venue_court(client, **court_fields):
    venue = client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()
    payload = {
        "venue_public_id": venue["public_id"],
        "name": "C1",
        "sport": "futsal",
        "price_weekday": 100000,
        "price_weekend": 150000,
    }
    payload.update(court_fields)
    res = client.post("/v1/courts", json=payload)
    assert res.status_code in (200, 201), res.text
    return venue, res.json()


def _quote(client, court_public_id, day=WEEKDAY, hour=17):
    res = client.get(
        "/v1/pricing/quote",
        params={
            "court_public_id": court_public_id,
            "starts_at": f"{day}T{hour:02d}:00:00",
            "ends_at": f"{day}T{hour + 1:02d}:00:00",
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_peak_fields_round_trip():
    client = _client()
    try:
        _, court = _venue_court(
            client,
            price_peak=200000,
            peak_start_hour=17,
            peak_end_hour=21,
        )
        assert court["price_peak"] == 200000
        assert court["peak_start_hour"] == 17
        assert court["peak_end_hour"] == 21

        # The listing carries them too, so the manager panel can show the window.
        listed = [
            c for c in client.get("/v1/courts").json() if c["public_id"] == court["public_id"]
        ][0]
        assert listed["price_peak"] == 200000
        assert listed["peak_start_hour"] == 17
    finally:
        app.dependency_overrides.clear()


def test_peak_applies_inside_window_and_day_rate_outside():
    client = _client()
    try:
        _, court = _venue_court(
            client,
            price_peak=200000,
            peak_start_hour=17,
            peak_end_hour=21,
        )
        cid = court["public_id"]

        # Inside the window (17–20 inclusive as start hours) → peak rate.
        assert _quote(client, cid, hour=17)["total"] == 200000
        assert _quote(client, cid, hour=20)["total"] == 200000
        # The window is half-open: hour 21 falls back to the weekday rate.
        assert _quote(client, cid, hour=21)["total"] == 100000
        # Before the window → weekday rate.
        assert _quote(client, cid, hour=16)["total"] == 100000
    finally:
        app.dependency_overrides.clear()


def test_peak_is_off_until_all_three_fields_are_set():
    client = _client()
    try:
        # A window without a rate cannot price anything, so it is a 422 rather
        # than a silently-inactive peak the manager cannot see.
        venue_id = client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()[
            "public_id"
        ]
        res = client.post(
            "/v1/courts",
            json={
                "venue_public_id": venue_id,
                "name": "C1",
                "sport": "futsal",
                "price_weekday": 100000,
                "price_weekend": 150000,
                "price_peak": 200000,
            },
        )
        assert res.status_code == 422

        # With no peak fields at all, the day rate books every hour.
        court = client.post(
            "/v1/courts",
            json={
                "venue_public_id": venue_id,
                "name": "C2",
                "sport": "futsal",
                "price_weekday": 100000,
                "price_weekend": 150000,
            },
        ).json()
        assert _quote(client, court["public_id"], hour=18)["total"] == 100000
    finally:
        app.dependency_overrides.clear()


def test_half_set_peak_window_is_rejected():
    client = _client()
    try:
        # A window without a rate cannot price anything, so it is a 422.
        res = client.post(
            "/v1/courts",
            json={
                "venue_public_id": client.post(
                    "/v1/venues", json={"name": "GOR", "address": "Jkt"}
                ).json()["public_id"],
                "name": "C1",
                "sport": "futsal",
                "price_weekday": 100000,
                "price_weekend": 150000,
                "peak_start_hour": 17,
                "peak_end_hour": 21,
            },
        )
        assert res.status_code == 422

        # A backwards window (start >= end) is likewise refused.
        venue_id = client.post("/v1/venues", json={"name": "G2", "address": "Jkt"}).json()[
            "public_id"
        ]
        res = client.post(
            "/v1/courts",
            json={
                "venue_public_id": venue_id,
                "name": "C2",
                "sport": "futsal",
                "price_weekday": 100000,
                "price_weekend": 150000,
                "price_peak": 200000,
                "peak_start_hour": 21,
                "peak_end_hour": 17,
            },
        )
        assert res.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_generated_slots_carry_peak_rate_per_hour():
    """Slot generation must price each hour, not the whole day."""
    client = _client()
    try:
        _, court = _venue_court(
            client,
            price_peak=200000,
            peak_start_hour=12,
            peak_end_hour=14,
        )
        # The venue's default hours already open 08:00–22:00 every day, so no
        # hours need setting here.
        gen = client.post(
            "/v1/slots/generate",
            json={
                "court_public_id": court["public_id"],
                "from_day": WEEKDAY,
                "to_day": WEEKDAY,
            },
        )
        assert gen.status_code == 201, gen.text
        assert gen.json()["created"] > 0

        slots = client.get(
            "/v1/slots",
            params={"court_public_id": court["public_id"], "day": WEEKDAY},
        ).json()
        by_hour = {s["starts_at"][11:13]: s["price"] for s in slots}
        # The peak window (12, 13) is priced at peak; the rest at weekday.
        assert by_hour["12"] == 200000
        assert by_hour["13"] == 200000
        assert by_hour["11"] == 100000
        assert by_hour["14"] == 100000
    finally:
        app.dependency_overrides.clear()


def test_clearing_peak_turns_it_off():
    client = _client()
    try:
        _, court = _venue_court(
            client,
            price_peak=200000,
            peak_start_hour=17,
            peak_end_hour=21,
        )
        # Explicit nulls clear the window (not "leave unchanged").
        cleared = client.patch(
            f"/v1/courts/{court['public_id']}",
            json={"price_peak": None, "peak_start_hour": None, "peak_end_hour": None},
        )
        assert cleared.status_code == 200, cleared.text
        body = cleared.json()
        assert body["price_peak"] is None
        assert body["peak_start_hour"] is None
        assert _quote(client, court["public_id"], hour=18)["total"] == 100000
    finally:
        app.dependency_overrides.clear()


def test_peak_overrides_weekend_rate_too():
    """Peak is a flat premium: it wins on a weekend hour as well."""
    client = _client()
    try:
        _, court = _venue_court(
            client,
            price_peak=200000,
            peak_start_hour=17,
            peak_end_hour=21,
        )
        # Saturday 2026-10-24 is a weekend day.
        weekend = _quote(client, court["public_id"], day="2026-10-24", hour=18)
        assert weekend["total"] == 200000
        # A non-peak weekend hour keeps the weekend rate.
        assert _quote(client, court["public_id"], day="2026-10-24", hour=10)["total"] == 150000
    finally:
        app.dependency_overrides.clear()


def _slots_by_hour(client, court_id, day=WEEKDAY):
    rows = client.get("/v1/slots", params={"court_public_id": court_id, "day": day}).json()
    return {s["starts_at"][11:13]: s for s in rows}


def test_rate_change_reprices_open_slots_but_not_booked_ones():
    """Slots are priced at generation, and generate skips existing rows — so a
    new rate has to reach open hours itself or quote keeps charging the old one.
    A booked hour keeps the price the customer already agreed to.
    """
    client = _client()
    try:
        _, court = _venue_court(client)
        cid = court["public_id"]
        client.post(
            "/v1/slots/generate",
            json={"court_public_id": cid, "from_day": WEEKDAY, "to_day": WEEKDAY},
        )
        before = _slots_by_hour(client, cid)
        assert before["10"]["price"] == 100000

        # Sell one hour first; its price is now an agreement, not a rate.
        booked = client.post(
            "/v1/bookings",
            json={
                "slot_public_id": before["10"]["public_id"],
                "customer_name": "Budi",
                "customer_contact": "0812",
            },
        )
        assert booked.status_code == 201, booked.text

        res = client.patch(f"/v1/courts/{cid}", json={"price_weekday": 120000})
        assert res.status_code == 200, res.text

        after = _slots_by_hour(client, cid)
        # Open hours moved to the new rate...
        assert after["11"]["price"] == 120000
        assert after["16"]["price"] == 120000
        # ...and the sold one did not.
        assert after["10"]["status"] == "booked"
        assert after["10"]["price"] == 100000

        # The quote agrees with both: it reads the slot rows.
        assert _quote(client, cid, hour=11)["total"] == 120000
        assert _quote(client, cid, hour=10)["total"] == 100000
    finally:
        app.dependency_overrides.clear()


def test_setting_a_peak_window_reaches_slots_that_already_exist():
    """The manager can add peak hours after generating the schedule."""
    client = _client()
    try:
        _, court = _venue_court(client)
        cid = court["public_id"]
        client.post(
            "/v1/slots/generate",
            json={"court_public_id": cid, "from_day": WEEKDAY, "to_day": WEEKDAY},
        )
        assert _slots_by_hour(client, cid)["18"]["price"] == 100000

        res = client.patch(
            f"/v1/courts/{cid}",
            json={"price_peak": 250000, "peak_start_hour": 17, "peak_end_hour": 22},
        )
        assert res.status_code == 200, res.text

        after = _slots_by_hour(client, cid)
        # Inside [17, 22) the existing rows now carry the premium...
        assert after["17"]["price"] == 250000
        assert after["21"]["price"] == 250000
        # ...and hours outside it keep the day rate. Half-open: 22 is not peak.
        assert after["16"]["price"] == 100000

        assert _quote(client, cid, hour=18)["total"] == 250000
        assert _quote(client, cid, hour=16)["total"] == 100000
    finally:
        app.dependency_overrides.clear()


def test_slots_in_the_past_keep_the_price_they_had():
    """Repricing only looks forward: history is not rewritten by a rate change."""
    client = _client()
    try:
        _, court = _venue_court(client)
        cid = court["public_id"]
        # An explicit slot on a day that has already gone by (2026-10-01).
        made = client.post(
            "/v1/slots",
            json=[
                {
                    "court_public_id": cid,
                    "starts_at": "2026-10-01T10:00:00",
                    "ends_at": "2026-10-01T11:00:00",
                    "price": 90000,
                }
            ],
        )
        assert made.status_code in (200, 201), made.text

        res = client.patch(f"/v1/courts/{cid}", json={"price_weekday": 120000})
        assert res.status_code == 200, res.text

        old = _slots_by_hour(client, cid, day="2026-10-01")
        assert old["10"]["price"] == 90000
    finally:
        app.dependency_overrides.clear()
