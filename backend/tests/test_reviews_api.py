"""A rating has to be earned by a visit.

This is the whole point of the feature: a venue's reputation comes from people
who played there, so a rating is only accepted from a customer whose booking
at that venue has already started and was not cancelled. Without that gate
anyone can write any number from anywhere, and the average stops meaning
anything.

The other rule worth pinning: one rating per person per venue. Re-submitting
updates the earlier opinion rather than adding a row, which is what people
expect from a rating form and what stops an average being padded by clicking
submit repeatedly.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.review import Review

# Today, so a slot generated for today has already started.
DAY = "2026-10-18"


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
    client = TestClient(app)
    client.testing_session = TestingSession
    return client


def _venue_court(client: TestClient) -> dict:
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
    return {"venue": venue, "court": court}


def _generate(client: TestClient, court: dict, day: str) -> None:
    client.post(
        "/v1/slots/generate",
        json={"court_public_id": court["public_id"], "from_day": day, "to_day": day},
    )


def _first_hour(client: TestClient, court: dict, day: str) -> dict:
    data = client.get(
        "/v1/availability/hours",
        params={"court_public_id": court["public_id"], "day": day},
    ).json()
    free = next(h for h in data["hours"] if h["status"] == "available")
    starts_at = free["starts_at"]
    hour = int(starts_at[11:13])
    return {"starts_at": starts_at, "ends_at": f"{day}T{hour + 1:02d}:00:00"}


def _book(client: TestClient, court: dict, day: str, contact: str, headers=None) -> dict:
    return client.post(
        "/v1/bookings/range",
        json={
            "court_public_id": court["public_id"],
            **_first_hour(client, court, day),
            "customer_name": "Ana",
            "customer_contact": contact,
        },
        headers=headers or {},
    )


def _confirm(client: TestClient, booked: dict, headers=None) -> None:
    """A booking only counts once the venue confirms it."""
    client.post(
        f"/v1/bookings/groups/{booked['group_public_id']}/confirm", headers=headers or {}
    )


def _sign_in(client: TestClient, email: str = "ana@example.test") -> dict:
    out = client.post(
        "/v1/customers/register",
        json={
            "email": email,
            "password": "correct horse",
            "display_name": "Ana",
            "phone": "0812000001",
        },
    )
    assert out.status_code == 201, out.text
    return {"X-Customer-Token": out.json()["token"]}


def _reviews(client: TestClient) -> list[Review]:
    db = client.testing_session()
    rows = db.scalars(select(Review)).all()
    db.close()
    return rows


def test_a_visitor_who_has_played_can_rate():
    client = _client()
    places = _venue_court(client)
    _generate(client, places["court"], DAY)
    booked = _book(client, places["court"], DAY, "0812000001").json()
    _confirm(client, booked)

    out = client.post(
        "/v1/reviews",
        params={"customer_contact": "0812000001"},
        json={
            "venue_public_id": places["venue"]["public_id"],
            "rating": 5,
            "comment": "Cold floor",
        },
    )
    assert out.status_code == 201, out.text
    assert out.json()["rating"] == 5
    assert out.json()["comment"] == "Cold floor"


def test_a_rating_needs_a_visit():
    client = _client()
    places = _venue_court(client)
    out = client.post(
        "/v1/reviews",
        params={"customer_contact": "0812000009"},
        json={"venue_public_id": places["venue"]["public_id"], "rating": 1},
    )
    assert out.status_code == 403
    assert "played" in out.json()["detail"].lower()


def test_a_booking_that_has_not_happened_yet_does_not_count():
    """A booking for next week is not an opinion yet."""
    client = _client()
    places = _venue_court(client)
    future = (datetime.now(UTC) + timedelta(days=7)).date().isoformat()
    _generate(client, places["court"], future)
    booked = _book(client, places["court"], future, "0812000001").json()
    _confirm(client, booked)

    out = client.post(
        "/v1/reviews",
        params={"customer_contact": "0812000001"},
        json={"venue_public_id": places["venue"]["public_id"], "rating": 5},
    )
    assert out.status_code == 403


def test_a_cancelled_visit_does_not_earn_a_rating():
    client = _client()
    places = _venue_court(client)
    _generate(client, places["court"], DAY)
    booked = _book(client, places["court"], DAY, "0812000001").json()
    _confirm(client, booked)
    client.post(
        f"/v1/bookings/groups/{booked['group_public_id']}/cancel",
        params={"customer_contact": "0812000001"},
    )

    out = client.post(
        "/v1/reviews",
        params={"customer_contact": "0812000001"},
        json={"venue_public_id": places["venue"]["public_id"], "rating": 5},
    )
    assert out.status_code == 403


def test_rating_twice_updates_the_first_opinion():
    """One row per person per venue, so the average cannot be padded."""
    client = _client()
    places = _venue_court(client)
    _generate(client, places["court"], DAY)
    booked = _book(client, places["court"], DAY, "0812000001").json()
    _confirm(client, booked)

    body = {"venue_public_id": places["venue"]["public_id"], "rating": 2}
    assert (
        client.post(
            "/v1/reviews", params={"customer_contact": "0812000001"}, json=body
        ).status_code
        == 201
    )
    second = client.post(
        "/v1/reviews",
        params={"customer_contact": "0812000001"},
        json={**body, "rating": 4, "comment": "Changed my mind"},
    )
    assert second.status_code == 200
    assert second.json()["rating"] == 4
    assert len(_reviews(client)) == 1


def test_the_contact_is_compared_digit_wise():
    """Two spellings of one number must be one reviewer.

    `0812-0000-001` and `+62 812-0000-001` are the same person, so the second
    rating updates the first instead of adding a row. If this ever drifts back
    to a string compare, an average becomes trivially inflatable.
    """
    client = _client()
    places = _venue_court(client)
    _generate(client, places["court"], DAY)
    booked = _book(client, places["court"], DAY, "0812-0000-001").json()
    _confirm(client, booked)

    first = client.post(
        "/v1/reviews",
        params={"customer_contact": "0812-0000-001"},
        json={"venue_public_id": places["venue"]["public_id"], "rating": 5},
    )
    assert first.status_code == 201

    again = client.post(
        "/v1/reviews",
        params={"customer_contact": "+62 812-0000-001"},
        json={
            "venue_public_id": places["venue"]["public_id"],
            "rating": 1,
            "comment": "Changed my mind",
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["rating"] == 1
    assert len(_reviews(client)) == 1


def test_a_rating_outside_one_to_five_is_rejected():
    client = _client()
    places = _venue_court(client)
    _generate(client, places["court"], DAY)
    booked = _book(client, places["court"], DAY, "0812000001").json()
    _confirm(client, booked)

    out = client.post(
        "/v1/reviews",
        params={"customer_contact": "0812000001"},
        json={"venue_public_id": places["venue"]["public_id"], "rating": 6},
    )
    assert out.status_code == 422


def test_the_summary_averages_what_was_left():
    client = _client()
    places = _venue_court(client)
    _generate(client, places["court"], DAY)
    for index, stars in enumerate([5, 4, 2]):
        contact = f"081200000{index}"
        booked = _book(client, places["court"], DAY, contact).json()
        _confirm(client, booked)
        client.post(
            "/v1/reviews",
            params={"customer_contact": contact},
            json={"venue_public_id": places["venue"]["public_id"], "rating": stars},
        )

    out = client.get(
        "/v1/reviews/summary", params={"venue_public_id": places["venue"]["public_id"]}
    )
    assert out.status_code == 200
    body = out.json()
    assert body["count"] == 3
    assert body["average"] == 3.7
    assert body["distribution"]["5"] == 1
    assert body["distribution"]["2"] == 1


def test_an_unrated_venue_reports_zero_rather_than_failing():
    """A venue nobody has rated yet still needs a number for its page."""
    client = _client()
    places = _venue_court(client)
    out = client.get(
        "/v1/reviews/summary", params={"venue_public_id": places["venue"]["public_id"]}
    )
    assert out.status_code == 200
    assert out.json()["count"] == 0
    assert out.json()["average"] == 0.0


def test_anyone_can_read_the_reviews():
    """A prospective customer is exactly who needs to see the reputation."""
    client = _client()
    places = _venue_court(client)
    _generate(client, places["court"], DAY)
    booked = _book(client, places["court"], DAY, "0812000001").json()
    _confirm(client, booked)
    client.post(
        "/v1/reviews",
        params={"customer_contact": "0812000001"},
        json={
            "venue_public_id": places["venue"]["public_id"],
            "rating": 5,
            "comment": "Great light",
        },
    )

    out = client.get("/v1/reviews", params={"venue_public_id": places["venue"]["public_id"]})
    assert out.status_code == 200
    assert out.headers["x-total-count"] == "1"
    rows = out.json()
    assert rows[0]["comment"] == "Great light"
    assert rows[0]["mine"] is False


def test_a_reviewer_is_told_which_one_is_theirs():
    client = _client()
    places = _venue_court(client)
    _generate(client, places["court"], DAY)
    headers = _sign_in(client)
    booked = _book(client, places["court"], DAY, "0812000001", headers=headers).json()
    _confirm(client, booked)
    client.post(
        "/v1/reviews",
        headers=headers,
        json={"venue_public_id": places["venue"]["public_id"], "rating": 5},
    )

    out = client.get(
        "/v1/reviews",
        params={"venue_public_id": places["venue"]["public_id"]},
        headers=headers,
    )
    assert out.json()[0]["mine"] is True


def test_an_unknown_venue_is_a_404_not_an_empty_list():
    client = _client()
    out = client.get(
        "/v1/reviews",
        params={"venue_public_id": "55555555-5555-5555-5555-555555555555"},
    )
    assert out.status_code == 404


def test_an_empty_comment_reads_as_no_comment():
    """A blank box should not become a one-space comment."""
    client = _client()
    places = _venue_court(client)
    _generate(client, places["court"], DAY)
    booked = _book(client, places["court"], DAY, "0812000001").json()
    _confirm(client, booked)

    out = client.post(
        "/v1/reviews",
        params={"customer_contact": "0812000001"},
        json={
            "venue_public_id": places["venue"]["public_id"],
            "rating": 4,
            "comment": "   ",
        },
    )
    assert out.status_code == 201
    assert out.json()["comment"] is None