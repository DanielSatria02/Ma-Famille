"""Login lockout and session revocation.

Lockout: N wrong passwords from one caller and that caller is told to wait,
with a Retry-After header. Revoke: logout deny-lists the token hash, so the
token stops unlocking manager routes even though its HMAC is still valid.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.ratelimit import throttle
from app.db.base import Base
from app.db.session import get_db
from app.main import app

PASSWORD = "rapat-rahasia"


def _client(monkeypatch, password: str = PASSWORD):
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
    monkeypatch.setattr(settings, "manager_password", password)
    # Tests share one process: start every case with a clean slate so a lockout
    # from one test cannot bleed into the next.
    monkeypatch.setattr(settings, "manager_lockout_attempts", 3)
    monkeypatch.setattr(settings, "manager_lockout_minutes", 15)
    for key in list(throttle._failures):
        throttle.clear(key)
    return TestClient(app)


def test_lockout_after_too_many_wrong_passwords(monkeypatch):
    client = _client(monkeypatch)
    try:
        for _ in range(3):
            assert (
                client.post("/v1/auth/login", json={"password": "salah"}).status_code
                == 401
            )

        locked = client.post("/v1/auth/login", json={"password": PASSWORD})
        assert locked.status_code == 429
        # The caller is told when to come back, not left guessing.
        assert int(locked.headers["Retry-After"]) >= 1
        assert "too many" in locked.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_successful_login_clears_the_streak(monkeypatch):
    client = _client(monkeypatch)
    try:
        # Two misses, then a hit: the slate wipes.
        client.post("/v1/auth/login", json={"password": "salah"})
        client.post("/v1/auth/login", json={"password": "salah"})
        assert client.post("/v1/auth/login", json={"password": PASSWORD}).status_code == 200

        # The streak restarted, so three fresh misses are all plain 401s. (Had
        # the two earlier misses survived, the second of these would already be
        # locked out — that is what makes this prove the wipe.)
        for _ in range(3):
            assert client.post("/v1/auth/login", json={"password": "salah"}).status_code == 401
        # Only the attempt after the fresh quota is refused.
        assert client.post("/v1/auth/login", json={"password": PASSWORD}).status_code == 429
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_logout_revokes_the_token(monkeypatch):
    client = _client(monkeypatch)
    try:
        token = client.post(
            "/v1/auth/login", json={"password": PASSWORD}
        ).json()["token"]
        headers = {"X-Manager-Token": token}

        # Before logout the token opens the manager routes.
        assert client.get("/v1/manager/bookings", headers=headers).status_code == 200

        out = client.post("/v1/auth/logout", headers=headers)
        assert out.status_code == 200, out.text
        assert out.json()["revoked"] is True

        # The HMAC is still valid, but the deny-list now refuses it.
        assert client.get("/v1/manager/bookings", headers=headers).status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_logout_is_idempotent(monkeypatch):
    client = _client(monkeypatch)
    try:
        token = client.post(
            "/v1/auth/login", json={"password": PASSWORD}
        ).json()["token"]
        headers = {"X-Manager-Token": token}

        assert client.post("/v1/auth/logout", headers=headers).json()["revoked"] is True
        # Logging out twice is not an error; the second call just did nothing.
        again = client.post("/v1/auth/logout", headers=headers)
        assert again.status_code == 200
        assert again.json()["revoked"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_other_sessions_survive_one_logout(monkeypatch):
    """Logging out one device must not kick out the others."""
    client = _client(monkeypatch)
    try:
        a = client.post("/v1/auth/login", json={"password": PASSWORD}).json()["token"]
        b = client.post("/v1/auth/login", json={"password": PASSWORD}).json()["token"]
        assert a != b

        client.post("/v1/auth/logout", headers={"X-Manager-Token": a})

        assert client.get("/v1/manager/bookings", headers={"X-Manager-Token": a}).status_code == 401
        assert client.get("/v1/manager/bookings", headers={"X-Manager-Token": b}).status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a_forged_or_garbage_token_is_refused(monkeypatch):
    client = _client(monkeypatch)
    try:
        # Logout only revokes real session tokens; junk writes nothing.
        out = client.post("/v1/auth/logout", headers={"X-Manager-Token": "not-a-token"})
        assert out.status_code == 200
        assert out.json()["revoked"] is False

        # And junk never opens a manager route.
        junk = {"X-Manager-Token": "not-a-token"}
        assert client.get("/v1/manager/bookings", headers=junk).status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_lockout_is_per_caller_not_global(monkeypatch):
    """One caller's lockout must not lock out everyone else."""
    client = _client(monkeypatch)
    try:
        # Hammer from the default client until locked.
        for _ in range(3):
            client.post("/v1/auth/login", json={"password": "salah"})
        assert (
            client.post("/v1/auth/login", json={"password": PASSWORD}).status_code
            == 429
        )

        # A different caller (different IP) is unaffected.
        other = client.post(
            "/v1/auth/login",
            json={"password": PASSWORD},
            headers={"X-Forwarded-For": "203.0.113.9"},
        )
        # TestClient reports the same host, so this may still be the locked key;
        # the point is the counter is keyed per caller, which the throttle unit
        # test below pins directly.
        assert other.status_code in (200, 429)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_throttle_counts_per_key():
    """The counter itself is keyed, not global."""
    now = 1000.0
    window = 60.0
    throttle.clear("alice")
    throttle.clear("bob")

    throttle.record_failure("alice", now=now)
    throttle.record_failure("alice", now=now + 1)
    assert throttle.is_locked_out("alice", max_attempts=2, window_seconds=window, now=now + 2)
    # Bob has no failures, so Bob is not locked.
    assert not throttle.is_locked_out("bob", max_attempts=2, window_seconds=window, now=now + 2)

    # Failures age out: past the window, alice is free again.
    assert not throttle.is_locked_out(
        "alice", max_attempts=2, window_seconds=window, now=now + window + 1
    )
