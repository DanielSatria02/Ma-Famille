"""What happens when a route crashes.

A crash used to answer with Starlette's plain-text 500, which carries no CORS
headers. The browser blocked it, the client never saw a response, and the
dashboard said the server was not reachable — for a crash on a server that
was answering perfectly well.
"""

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.main import app

router = APIRouter(prefix="/v1/testing")


@router.get("/boom")
def boom():
    raise RuntimeError("deliberate crash for the test")


# The route is added after the app was created, so the middleware stack is the
# one production uses.
app.include_router(router)

client = TestClient(app, raise_server_exceptions=False)


def test_crash_answers_json_not_plain_text():
    res = client.get("/v1/testing/boom")
    assert res.status_code == 500
    assert res.headers["content-type"].startswith("application/json")
    body = res.json()
    assert "detail" in body
    assert body["request_id"]


def test_crash_carries_cors_headers():
    res = client.get(
        "/v1/testing/boom", headers={"Origin": "http://localhost:5173"}
    )
    assert res.status_code == 500
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_crash_does_not_leak_the_traceback():
    res = client.get("/v1/testing/boom")
    text = res.text
    assert "RuntimeError" not in text
    assert "deliberate crash" not in text


def test_crash_response_names_a_request_id_that_the_header_repeats():
    res = client.get("/v1/testing/boom")
    assert res.headers["x-request-id"] == res.json()["request_id"]


def test_healthy_routes_are_untouched():
    assert client.get("/v1/health").status_code == 200
