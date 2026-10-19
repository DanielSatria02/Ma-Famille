"""Promo codes: a manager creates one, a customer redeems it, the discount
lands on the booking and the code's use count goes up.

Covers the refusal reasons (unknown, expired, wrong venue, maxed out), the
public dry-run check, and that a multi-hour group takes the discount once.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Monday 2026-10-19, a weekday: the day rate is 100000/hour.
DAY = "2026-10-19"


def _client() -> TestClient:
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


def _teardown():
    app.dependency_overrides.pop(get_db, None)


def _manager_headers(client: TestClient, monkeypatch) -> dict:
    """Set a manager password (conftest blanks it) and log in."""
    monkeypatch.setattr(settings, "manager_password", "kata-sandi")
    login = client.post(
        "/v1/auth/login",
        json={"email": "manajer@ma-famille.test", "password": "kata-sandi"},
    )
    assert login.status_code == 200, login.text
    return {"X-Manager-Token": login.json()["token"]}


def _venue_court(client: TestClient) -> dict:
    """Venue + court + generated slots. Call BEFORE a password is set,
    because creating them is a manager route."""
    venue = client.post("/v1/venues", json={"name": "GOR", "address": "Jkt"}).json()
    court = client.post(
        "/v1/courts",
        json={
            "venue_public_id": venue["public_id"],
            "name": "C1",
            "sport": "padel",
            "price_weekday": 100000,
            "price_weekend": 150000,
        },
    ).json()
    client.post(
        "/v1/slots/generate",
        json={"court_public_id": court["public_id"], "from_day": DAY, "to_day": DAY},
    )
    return {"venue": venue, "court": court}


def _make_code(client: TestClient, headers: dict, **overrides) -> dict:
    body = {"code": "HEMAT20", "kind": "percent", "value": 20}
    for key, value in list(overrides.items()):
        # datetimes must cross the wire as ISO strings, not python objects.
        body[key] = value.isoformat() if hasattr(value, "isoformat") else value
    res = client.post("/v1/promotions", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _single_slot(client: TestClient, court_id: str, price: int = 120000) -> str:
    """One explicit slot with a known price, no generation involved.

    The court is passed in rather than cached: every test gets a fresh
    in-memory database, so a remembered id from an earlier test is a 404.
    """
    res = client.post(
        "/v1/slots",
        json=[
            {
                "court_public_id": court_id,
                "starts_at": f"{DAY}T15:00:00",
                "ends_at": f"{DAY}T16:00:00",
                "price": price,
            }
        ],
    )
    assert res.status_code in (200, 201), res.text
    return res.json()[0]["public_id"]


def test_manager_promo_routes_are_closed_without_a_token(monkeypatch):
    client = _client()
    try:
        # A password is what closes manager routes; with none set they are open
        # for local dev, so set one first and then ask without a token.
        monkeypatch.setattr(settings, "manager_password", "kata-sandi")
        assert client.get("/v1/promotions").status_code == 401
        assert (
            client.post("/v1/promotions", json={"code": "X1", "value": 10}).status_code
            == 401
        )
        # A wrong token stays out too.
        junk = {"X-Manager-Token": "bukan-token"}
        assert client.get("/v1/promotions", headers=junk).status_code == 401
    finally:
        _teardown()


def test_promo_crud_round_trip_and_duplicate_is_conflict(monkeypatch):
    client = _client()
    try:
        headers = _manager_headers(client, monkeypatch)
        made = _make_code(client, headers, value=15)
        assert made["code"] == "HEMAT20"
        assert made["kind"] == "percent"
        assert made["used_count"] == 0

        # A second row with the same code would be unreachable by its own code.
        dup = client.post(
            "/v1/promotions",
            json={"code": "hemat20", "kind": "percent", "value": 15},
            headers=headers,
        )
        assert dup.status_code == 409, dup.text

        listing = client.get("/v1/promotions", headers=headers)
        assert listing.status_code == 200, listing.text
        assert [row["code"] for row in listing.json()] == ["HEMAT20"]

        patched = client.patch(
            f"/v1/promotions/{made['public_id']}",
            json={"value": 30, "is_active": False},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["value"] == 30
        assert patched.json()["is_active"] is False
    finally:
        _teardown()


def test_codes_are_case_insensitive_and_check_reports_the_discount(monkeypatch):
    client = _client()
    try:
        setup = _venue_court(client)
        court_id = setup["court"]["public_id"]
        headers = _manager_headers(client, monkeypatch)
        _make_code(client, headers, value=20)

        # The customer tests a lower-case spelling before booking.
        checked = client.get(
            "/v1/promotions/check",
            params={
                "code": "hemat20",
                "court_public_id": court_id,
                "starts_at": f"{DAY}T09:00:00",
                "ends_at": f"{DAY}T12:00:00",
            },
        )
        assert checked.status_code == 200, checked.text
        body = checked.json()
        # 3 hours x 100000 = 300000 gross, 20% off.
        assert body["ok"] is True
        assert body["code"] == "HEMAT20"
        assert body["gross"] == 300000
        assert body["discount"] == 60000
        assert body["amount_due"] == 240000

        # The dry run must not spend the code.
        fresh = client.get("/v1/promotions", headers=headers).json()
        assert fresh[0]["used_count"] == 0
    finally:
        _teardown()


def test_check_refuses_an_unknown_code_in_words():
    client = _client()
    try:
        res = client.get("/v1/promotions/check", params={"code": "TIDAK-ADA"})
        assert res.status_code == 200, res.text
        assert res.json()["ok"] is False
        assert res.json()["reason"] == "that code does not exist"
    finally:
        _teardown()


def test_percent_discount_applies_to_a_single_booking(monkeypatch):
    client = _client()
    try:
        # Court before the password: creating one is a manager route.
        court_id = _venue_court(client)["court"]["public_id"]
        slot_id = _single_slot(client, court_id, price=120000)
        headers = _manager_headers(client, monkeypatch)
        _make_code(client, headers, value=25)

        res = client.post(
            "/v1/bookings",
            json={
                "slot_public_id": slot_id,
                "customer_name": "Budi",
                "customer_contact": "0812",
                "promo_code": "hemat20",
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["discount"] == 30000  # 25% of 120000
        assert body["promo_code"] == "HEMAT20"
        assert body["total"] == 90000

        # The code was spent exactly once.
        spent = client.get("/v1/promotions", headers=headers).json()
        assert spent[0]["used_count"] == 1
    finally:
        _teardown()


def test_amount_discount_is_capped_at_the_total(monkeypatch):
    client = _client()
    try:
        court_id = _venue_court(client)["court"]["public_id"]
        slot_id = _single_slot(client, court_id, price=120000)
        headers = _manager_headers(client, monkeypatch)
        # A generous flat code that exceeds the booking must not go negative.
        _make_code(client, headers, kind="amount", value=999999, code="GRATIS")

        res = client.post(
            "/v1/bookings",
            json={
                "slot_public_id": slot_id,
                "customer_name": "Budi",
                "customer_contact": "0812",
                "promo_code": "GRATIS",
            },
        )
        assert res.status_code == 201, res.text
        assert res.json()["discount"] == 120000
        assert res.json()["total"] == 0
    finally:
        _teardown()


def test_range_booking_takes_the_discount_only_once(monkeypatch):
    client = _client()
    try:
        setup = _venue_court(client)
        headers = _manager_headers(client, monkeypatch)
        _make_code(client, headers, kind="amount", value=50000, code="POTONG50")

        res = client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": setup["court"]["public_id"],
                "starts_at": f"{DAY}T09:00:00",
                "ends_at": f"{DAY}T12:00:00",
                "customer_name": "Budi",
                "customer_contact": "0812",
                "promo_code": "POTONG50",
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        # 3 hours x 100000 = 300000 gross, one flat 50000 off the group.
        assert body["hours"] == 3
        assert body["total"] == 250000
        # The discount sits on the first row only, so summing rows counts it once.
        assert [b["discount"] for b in body["bookings"]] == [50000, 0, 0]
        assert sum(b["discount"] for b in body["bookings"]) == 50000
        assert all(b["promo_code"] == "POTONG50" for b in body["bookings"])

        # Summing what each row costs equals the group total.
        assert sum(b["total"] for b in body["bookings"]) == body["total"]

        spent = client.get("/v1/promotions", headers=headers).json()
        assert spent[0]["used_count"] == 1
    finally:
        _teardown()


def test_a_refused_code_blocks_the_booking_and_writes_nothing(monkeypatch):
    client = _client()
    try:
        setup = _venue_court(client)
        headers = _manager_headers(client, monkeypatch)
        _make_code(
            client,
            headers,
            valid_to=datetime.now(UTC) - timedelta(days=1),
            code="LEWAT",
        )

        res = client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": setup["court"]["public_id"],
                "starts_at": f"{DAY}T09:00:00",
                "ends_at": f"{DAY}T11:00:00",
                "customer_name": "Budi",
                "customer_contact": "0812",
                "promo_code": "LEWAT",
            },
        )
        assert res.status_code == 422, res.text
        assert res.json()["detail"] == "that code has expired"

        # Nothing was booked and no use was counted.
        free = client.get(
            "/v1/availability/hours",
            params={"court_public_id": setup["court"]["public_id"], "day": DAY},
        ).json()
        by_hour = {e["hour"]: e["status"] for e in free["hours"]}
        assert by_hour[9] == "available" and by_hour[10] == "available"
        assert client.get("/v1/promotions", headers=headers).json()[0]["used_count"] == 0

        # The unknown-code path refuses the same way.
        bad = client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": setup["court"]["public_id"],
                "starts_at": f"{DAY}T09:00:00",
                "ends_at": f"{DAY}T11:00:00",
                "customer_name": "Budi",
                "customer_contact": "0812",
                "promo_code": "TIDAK-ADA",
            },
        )
        assert bad.status_code == 422
        assert bad.json()["detail"] == "that code does not exist"
    finally:
        _teardown()


def test_a_code_scoped_to_another_venue_is_refused(monkeypatch):
    client = _client()
    try:
        # Both venues first: creating one is a manager route, so it must happen
        # before a password exists or it comes back 401.
        other = client.post("/v1/venues", json={"name": "GOR Lain", "address": "Bdg"})
        setup = _venue_court(client)

        headers = _manager_headers(client, monkeypatch)
        # Scoped to a venue the booking does not belong to.
        _make_code(client, headers, venue_public_id=other.json()["public_id"], code="SINI")

        res = client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": setup["court"]["public_id"],
                "starts_at": f"{DAY}T09:00:00",
                "ends_at": f"{DAY}T11:00:00",
                "customer_name": "Budi",
                "customer_contact": "0812",
                "promo_code": "SINI",
            },
        )
        assert res.status_code == 422, res.text
        assert res.json()["detail"] == "that code is only valid for a different venue"
    finally:
        _teardown()


def test_max_uses_stops_the_next_redeem(monkeypatch):
    client = _client()
    try:
        setup = _venue_court(client)
        headers = _manager_headers(client, monkeypatch)
        _make_code(client, headers, max_uses=1, code="SEKALI")

        def book(tag: str, hour: int = 9):
            # Slots are checked before the promo, so the second attempt must use
            # free hours — otherwise it fails on the taken slot, not on the code.
            return client.post(
                "/v1/bookings/range",
                json={
                    "court_public_id": setup["court"]["public_id"],
                    "starts_at": f"{DAY}T{hour:02d}:00:00",
                    "ends_at": f"{DAY}T{hour + 2:02d}:00:00",
                    "customer_name": tag,
                    "customer_contact": "0812",
                    "promo_code": "SEKALI",
                },
            )

        assert book("pertama").status_code == 201

        second = book("kedua", hour=13)
        assert second.status_code == 422, second.text
        assert second.json()["detail"] == (
            "that code has been used the maximum number of times"
        )

        # The check agrees with what booking did.
        checked = client.get(
            "/v1/promotions/check", params={"code": "SEKALI"}
        ).json()
        assert checked["ok"] is False
        assert "maximum number of times" in checked["reason"]
    finally:
        _teardown()


def test_a_redeemed_code_cannot_be_deleted_but_can_be_switched_off(monkeypatch):
    client = _client()
    try:
        setup = _venue_court(client)
        headers = _manager_headers(client, monkeypatch)
        made = _make_code(client, headers, value=20)

        # Spending it once makes it evidence for why a past booking was cheaper.
        client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": setup["court"]["public_id"],
                "starts_at": f"{DAY}T09:00:00",
                "ends_at": f"{DAY}T11:00:00",
                "customer_name": "Budi",
                "customer_contact": "0812",
                "promo_code": "HEMAT20",
            },
        )

        gone = client.delete(
            f"/v1/promotions/{made['public_id']}", headers=headers
        )
        assert gone.status_code == 409, gone.text

        # Deactivating keeps the record and stops the redemptions.
        off = client.patch(
            f"/v1/promotions/{made['public_id']}",
            json={"is_active": False},
            headers=headers,
        )
        assert off.status_code == 200
        assert off.json()["is_active"] is False

        refused = client.post(
            "/v1/bookings/range",
            json={
                "court_public_id": setup["court"]["public_id"],
                "starts_at": f"{DAY}T13:00:00",
                "ends_at": f"{DAY}T15:00:00",
                "customer_name": "Lain",
                "customer_contact": "0813",
                "promo_code": "HEMAT20",
            },
        )
        assert refused.status_code == 422
        assert refused.json()["detail"] == "that code is no longer active"

        # An unused code still deletes outright.
        spare = _make_code(client, headers, code="BELUM")
        ok = client.delete(f"/v1/promotions/{spare['public_id']}", headers=headers)
        assert ok.status_code == 204, ok.text
        assert (
            client.delete(f"/v1/promotions/{spare['public_id']}", headers=headers).status_code
            == 404
        )
    finally:
        _teardown()
