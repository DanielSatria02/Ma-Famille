"""The payment gateway has to be reachable on a machine with no resolver.

The production server has egress but no working DNS: every resolver on port
53 is closed and the gateway refuses. A payment request that needs a name
looked up used to fail there with "Temporary failure in name resolution",
and the customer saw a dead checkout button.

So when the name cannot be resolved, it is looked up over HTTPS and the
request goes to the address — with the name kept for the TLS handshake and
the Host header, because the certificate belongs to the name.
"""

import socket

import httpx
import pytest

from app.services import doku


class FakeResponse:
    status_code = 200

    def json(self):
        return {"response": {"payment": {"url": "https://pay.test/x", "token_id": "t"}}}


def _name_error():
    """The failure a machine with no resolver gives."""
    error = httpx.ConnectError("name resolution failed")
    error.__cause__ = socket.gaierror(-3, "Temporary failure in name resolution")
    return error


def test_a_refused_request_is_not_retried(monkeypatch):
    """A refusal from DOKU is not a name problem, so it is passed on."""
    called = []

    def fake_post(url, **kwargs):
        called.append(url)
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(doku, "_address_for", lambda host: None)
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(doku, "resolve_over_https", lambda host: pytest.fail("must not resolve"))
    with pytest.raises(httpx.ConnectError):
        doku.post_to_doku(
            "https://doku.test/checkout/v1/payment", content=b"{}", headers={}
        )
    assert len(called) == 1


def test_a_name_that_cannot_be_resolved_is_looked_up_over_https(monkeypatch):
    asked = []

    def fake_post(url, **kwargs):
        raise _name_error()

    def fake_get(url, **kwargs):
        asked.append((url, kwargs.get("params")))
        response = httpx.Response(
            200,
            json={"Answer": [{"type": 1, "data": "147.139.176.73"}]},
            request=httpx.Request("GET", url),
        )
        return response

    sent = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def build_request(self, method, url, **kwargs):
            sent["method"] = method
            sent["url"] = url
            sent["headers"] = kwargs.get("headers", {})
            sent["extensions"] = kwargs.get("extensions", {})
            return httpx.Request(method, url)

        def send(self, request):
            return FakeResponse()

    monkeypatch.setattr(doku, "_resolver_answers", lambda host: False)
    monkeypatch.setattr(doku, "_ADDRESS_CACHE", {})
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "Client", FakeClient)

    response = doku.post_to_doku(
        "https://api-sandbox.doku.com/checkout/v1/payment",
        content=b"{}",
        headers={"Client-Id": "MCH-1"},
    )

    assert response.status_code == 200
    # The name was asked for over HTTPS.
    assert asked[0][0] == doku.DOH_ENDPOINT
    assert asked[0][1] == {"name": "api-sandbox.doku.com", "type": "A"}
    # The request went to the address, but kept the name for the handshake.
    assert sent["url"] == "https://147.139.176.73/checkout/v1/payment"
    assert sent["headers"]["Host"] == "api-sandbox.doku.com"
    assert sent["headers"]["Client-Id"] == "MCH-1"
    assert sent["extensions"]["sni_hostname"] == "api-sandbox.doku.com"


def test_a_name_without_an_address_is_an_error(monkeypatch):
    def fake_post(url, **kwargs):
        raise _name_error()

    def fake_get(url, **kwargs):
        return httpx.Response(
            200,
            json={"Answer": [{"type": 5, "data": "some.cname.example."}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(doku, "_address_for", lambda host: None)
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(doku.DokuError, match="no address"):
        doku.post_to_doku("https://doku.test/x", content=b"{}", headers={})


def test_the_checkout_goes_through_the_helper(monkeypatch):
    """The checkout and the refund both go through the fallback."""
    seen = []

    def fake_post_to_doku(url, **kwargs):
        seen.append(url)
        return FakeResponse()

    from app.core.config import settings

    monkeypatch.setattr(settings, "doku_client_id", "MCH-TEST")
    monkeypatch.setattr(settings, "doku_secret_key", "secret-test")
    monkeypatch.setattr(settings, "doku_base_url", "https://doku.test")
    monkeypatch.setattr(doku, "post_to_doku", fake_post_to_doku)

    doku.create_checkout(invoice_number="MAF-TEST", amount=10000, customer_name="Tester")
    assert seen == ["https://doku.test/checkout/v1/payment"]


def test_the_machine_is_asked_whether_it_can_resolve(monkeypatch):
    """A name the machine can look up is used as it is."""
    asked = []

    def fake_post(url, **kwargs):
        asked.append(url)
        return FakeResponse()

    monkeypatch.setattr(doku, "_resolver_answers", lambda host: True)
    monkeypatch.setattr(httpx, "post", fake_post)
    doku.post_to_doku("https://doku.test/x", content=b"{}", headers={})
    assert asked == ["https://doku.test/x"]


def test_a_machine_without_a_resolver_asks_over_https(monkeypatch):
    """A name the machine cannot look up is asked for over HTTPS first."""
    asked = []
    sent = {}

    def fake_get(url, **kwargs):
        asked.append((url, kwargs.get("params")))
        return httpx.Response(
            200,
            json={"Answer": [{"type": 1, "data": "147.139.176.73"}]},
            request=httpx.Request("GET", url),
        )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def build_request(self, method, url, **kwargs):
            sent["url"] = url
            return httpx.Request(method, url)

        def send(self, request):
            return FakeResponse()

    monkeypatch.setattr(doku, "_resolver_answers", lambda host: False)
    monkeypatch.setattr(doku, "_ADDRESS_CACHE", {})
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "Client", FakeClient)

    doku.post_to_doku("https://doku.test/x", content=b"{}", headers={})
    assert asked[0][1] == {"name": "doku.test", "type": "A"}
    assert sent["url"] == "https://147.139.176.73/x"


def test_the_verdict_is_remembered(monkeypatch):
    """The machine is asked once, not once per payment."""
    checks = []

    def fake_check(host):
        checks.append(host)
        return False

    def fake_get(url, **kwargs):
        return httpx.Response(
            200,
            json={"Answer": [{"type": 1, "data": "147.139.176.73"}]},
            request=httpx.Request("GET", url),
        )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def build_request(self, method, url, **kwargs):
            return httpx.Request(method, url)

        def send(self, request):
            return FakeResponse()

    monkeypatch.setattr(doku, "_resolver_answers", fake_check)
    monkeypatch.setattr(doku, "_ADDRESS_CACHE", {})
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "Client", FakeClient)

    doku.post_to_doku("https://doku.test/x", content=b"{}", headers={})
    doku.post_to_doku("https://doku.test/x", content=b"{}", headers={})
    assert len(checks) == 1


def test_a_resolver_that_answers_is_taken_at_its_word(monkeypatch):
    """A resolver that answers is used, and no lookup over HTTPS happens."""
    monkeypatch.setattr(doku, "_resolver_answers", lambda host: True)
    monkeypatch.setattr(doku, "_ADDRESS_CACHE", {})
    monkeypatch.setattr(
        doku, "resolve_over_https", lambda host: pytest.fail("must not look it up")
    )
    assert doku._address_for("doku.test") is None
