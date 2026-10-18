"""Customer accounts: register, sign in, prove identity, sign out.

A customer used to be only the contact string typed into the booking form,
so "My bookings" trusted whatever was entered. These tests pin the identity
that replaces it: a password that is stored hashed, a session token whose
hash is the only thing kept, and a sign-out that actually ends it.

Also covers the refusals, including that a wrong password and an unknown
email answer identically — telling the two apart is what makes credential
stuffing cheap.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.passwords import hash_password, verify_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.customer_session import CustomerSession

# A day far enough out to never collide with a real booking test.
DAY = "2026-11-02"


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
    # Expose the session factory so a test can age a token by hand.
    client.testing_session = TestingSession
    return client


def _register(client, email="ana@example.test", password="correct horse", **extra):
    return client.post(
        "/v1/customers/register",
        json={
            "email": email,
            "password": password,
            "display_name": extra.pop("display_name", "Ana"),
            **extra,
        },
    )


def test_register_creates_an_account_and_returns_a_token():
    client = _client()
    out = _register(client)
    assert out.status_code == 201
    body = out.json()
    assert body["token"]
    assert body["customer"]["email"] == "ana@example.test"
    assert body["customer"]["display_name"] == "Ana"
    # The token also rides in the header, so a client reading only headers works.
    assert out.headers["X-Customer-Token"] == body["token"]


def test_the_password_is_stored_hashed_never_in_the_clear():
    client = _client()
    _register(client, password="correct horse")

    from app.models.customer import Customer

    db = client.testing_session()
    row = db.scalars(select(Customer)).first()
    db.close()
    assert row is not None
    assert row.password_hash != "correct horse"
    assert row.password_hash.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse", row.password_hash)


def test_a_duplicate_email_is_refused_with_a_usable_reason():
    client = _client()
    assert _register(client).status_code == 201
    again = _register(client)
    assert again.status_code == 409
    assert "already registered" in again.json()["detail"]


def test_the_email_is_case_insensitive():
    client = _client()
    assert _register(client, email="Ana@Example.test").status_code == 201
    # A different case is the same account, so this is a duplicate, not a second.
    out = _register(client, email="ana@example.test")
    assert out.status_code == 409


def test_a_short_password_is_refused():
    client = _client()
    out = _register(client, password="short")
    assert out.status_code == 422


def test_a_malformed_email_is_refused():
    client = _client()
    for bad in ("not-an-email", "ana@", "@example.test", "ana@example"):
        out = _register(client, email=bad)
        assert out.status_code == 422, bad


def test_signing_in_with_the_right_password_returns_a_token():
    client = _client()
    _register(client, password="correct horse")
    out = client.post(
        "/v1/customers/login",
        json={"email": "ana@example.test", "password": "correct horse"},
    )
    assert out.status_code == 200
    assert out.json()["token"]


def test_a_wrong_password_and_an_unknown_email_answer_identically():
    """Deliberately the same: otherwise the pair tells an attacker which
    addresses have accounts, which is what makes credential stuffing work."""
    client = _client()
    _register(client)
    wrong = client.post(
        "/v1/customers/login",
        json={"email": "ana@example.test", "password": "not the one"},
    )
    unknown = client.post(
        "/v1/customers/login",
        json={"email": "nobody@example.test", "password": "whatever"},
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_me_answers_the_signed_in_customer_and_refuses_without_a_token():
    client = _client()
    out = _register(client)
    token = out.json()["token"]

    who = client.get("/v1/customers/me", headers={"X-Customer-Token": token})
    assert who.status_code == 200
    assert who.json()["email"] == "ana@example.test"

    assert client.get("/v1/customers/me").status_code == 401
    assert (
        client.get(
            "/v1/customers/me", headers={"X-Customer-Token": "not-a-real-token"}
        ).status_code
        == 401
    )


def test_signing_out_ends_the_session():
    client = _client()
    token = _register(client).json()["token"]
    headers = {"X-Customer-Token": token}
    assert client.get("/v1/customers/me", headers=headers).status_code == 200

    assert client.post("/v1/customers/logout", headers=headers).status_code == 204
    assert client.get("/v1/customers/me", headers=headers).status_code == 401


def test_signing_out_twice_is_not_an_error():
    client = _client()
    token = _register(client).json()["token"]
    headers = {"X-Customer-Token": token}
    assert client.post("/v1/customers/logout", headers=headers).status_code == 204
    # Already signed out is the state the caller asked for.
    assert client.post("/v1/customers/logout", headers=headers).status_code == 204


def test_an_expired_session_is_refused():
    client = _client()
    token = _register(client).json()["token"]
    headers = {"X-Customer-Token": token}
    assert client.get("/v1/customers/me", headers=headers).status_code == 200

    # Age the row behind the token, then ask again: the token is unchanged but
    # it no longer proves anything.
    db = client.testing_session()
    row = db.scalars(select(CustomerSession)).first()
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    db.close()

    assert client.get("/v1/customers/me", headers=headers).status_code == 401


def test_passwords_hash_and_verify_round_trip():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("correct hors", stored)
    # A different salt each time, so two accounts with one password do not
    # share a hash.
    assert hash_password("correct horse") != stored
    # A mangled stored value is a refusal, not a crash.
    assert not verify_password("correct horse", "garbage")
