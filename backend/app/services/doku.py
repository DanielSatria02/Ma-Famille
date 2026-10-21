"""DOKU non-SNAP signature helpers (Checkout + HTTP Notification).

Spec: developers.doku.com — headers `Client-Id`, `Request-Id`,
`Request-Timestamp` (UTC ISO8601), `Signature: HMACSHA256=<base64>`.
Component string joins the five parts with "\\n"; Digest is
base64(SHA-256(minified JSON body)). Notifications from DOKU use the
merchant Notification URL path as Request-Target.
"""

import base64
import hashlib
import hmac
import json
import socket
import struct
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.core.config import settings
from app.core.ids import uuid7


def utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_request_id() -> str:
    return str(uuid4())


def build_digest(body: bytes) -> str:
    return base64.b64encode(hashlib.sha256(body).digest()).decode()


def build_signature(
    *,
    client_id: str,
    request_id: str,
    timestamp: str,
    request_target: str,
    digest: str,
    secret: str,
) -> str:
    components = (
        f"Client-Id:{client_id}\n"
        f"Request-Id:{request_id}\n"
        f"Request-Timestamp:{timestamp}\n"
        f"Request-Target:{request_target}\n"
        f"Digest:{digest}"
    )
    mac = hmac.new(secret.encode(), components.encode(), hashlib.sha256).digest()
    return "HMACSHA256=" + base64.b64encode(mac).decode()


def verify_signature(
    *,
    signature: str,
    client_id: str,
    request_id: str,
    timestamp: str,
    request_target: str,
    digest: str,
    secret: str,
) -> bool:
    expected = build_signature(
        client_id=client_id,
        request_id=request_id,
        timestamp=timestamp,
        request_target=request_target,
        digest=digest,
        secret=secret,
    )
    return hmac.compare_digest(expected, signature)


CHECKOUT_TARGET = "/checkout/v1/payment"

# Where a name is looked up when the machine has no working resolver. The
# production VM has egress but no DNS: every resolver on port 53 is closed,
# and the gateway refuses. A name that cannot be resolved is asked for over
# HTTPS instead — the address is an IP, so it needs no lookup of its own.
DOH_ENDPOINT = "https://1.1.1.1/dns-query"


class DokuError(RuntimeError):
    pass


def _is_a_name_error(exc: BaseException) -> bool:
    """True when the address could not be looked up, rather than refused."""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, socket.gaierror):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def resolve_over_https(hostname: str) -> str:
    """Ask a resolver over HTTPS for the address of a host."""
    res = httpx.get(
        DOH_ENDPOINT,
        params={"name": hostname, "type": "A"},
        headers={"accept": "application/dns-json"},
        timeout=10,
    )
    if res.status_code != 200:
        raise DokuError(
            f"the name could not be looked up (DNS over HTTPS answered {res.status_code})"
        )
    try:
        answers = res.json().get("Answer", [])
    except ValueError:
        answers = []
    for answer in answers:
        if answer.get("type") == 1 and answer.get("data"):
            return str(answer["data"])
    raise DokuError(f"the name {hostname} has no address")


# Addresses looked up over HTTPS, with the time they were found. The gateway
# sits behind a load balancer, so the address is not a fixed one, but it does
# not change often either.
_ADDRESS_CACHE: dict[str, tuple[str, float, bool]] = {}
_ADDRESS_TTL_SECONDS = 300


def _cached_address(hostname: str) -> str | None:
    found = _ADDRESS_CACHE.get(hostname)
    if found is None:
        return None
    address, when, _resolves = found
    if time.monotonic() - when > _ADDRESS_TTL_SECONDS:
        return None
    return address or None


def _remember_address(hostname: str, address: str) -> None:
    _ADDRESS_CACHE[hostname] = (address, time.monotonic(), False)


def _resolver_answers(hostname: str) -> bool:
    """Does the machine's own resolver answer for this name?

    The check is a DNS query of its own, sent to the nameserver in
    /etc/resolv.conf, and it waits a second and a half at most. The usual
    library call cannot be used for this: on a server whose nameserver
    refuses the query, it hangs for the whole resolver timeout instead, so
    the answer would come after the payment had already been given up on.
    """
    servers = _configured_nameservers()
    if not servers:
        return False
    query = _dns_query(hostname)
    for server in servers:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.5)
        try:
            sock.sendto(query, (server, 53))
            data, _ = sock.recvfrom(2048)
        except (TimeoutError, OSError):
            continue
        finally:
            sock.close()
        if len(data) >= 4 and data[3] & 0x0F == 0:
            return True
    return False


def _configured_nameservers() -> list[str]:
    """The nameservers the machine is set to use."""
    servers: list[str] = []
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("nameserver"):
                    parts = line.split()
                    if len(parts) > 1:
                        servers.append(parts[1])
    except OSError:
        pass
    return servers


def _dns_query(hostname: str) -> bytes:
    """An A query for a name, built by hand."""
    header = struct.pack("!HHHHHH", 0x4D41, 0x0100, 1, 0, 0, 0)
    body = b""
    for part in hostname.split("."):
        body += bytes([len(part)]) + part.encode()
    body += b"\x00" + struct.pack("!HH", 1, 1)
    return header + body


def post_to_doku(
    url: str, *, content: bytes, headers: dict[str, str], timeout: int = 15
) -> httpx.Response:
    """POST to DOKU, working around a server with no working resolver.

    When the name cannot be resolved, it is looked up over HTTPS and the
    request goes to the address — with the name kept for the TLS handshake
    and the Host header, because the certificate belongs to the name and
    not to the address.
    """
    parts = urlsplit(url)
    hostname = parts.hostname
    if not hostname:
        return httpx.post(url, content=content, headers=headers, timeout=timeout)

    address = _address_for(hostname)
    if address is None:
        try:
            return httpx.post(url, content=content, headers=headers, timeout=timeout)
        except httpx.ConnectError as exc:
            if not _is_a_name_error(exc):
                raise
            address = resolve_over_https(hostname)
            _remember_address(hostname, address)

    target = f"https://{address}{parts.path}"
    if parts.query:
        target = f"{target}?{parts.query}"
    with httpx.Client(timeout=timeout) as client:
        request = client.build_request(
            "POST",
            target,
            content=content,
            headers={**headers, "Host": hostname},
            extensions={"sni_hostname": hostname},
        )
        return client.send(request)


def _address_for(hostname: str) -> str | None:
    """The address to use for a name, or None when the machine can look it up.

    The verdict is remembered for a while, because a machine that cannot
    resolve names will not start doing so between two payments — and asking
    again costs a second of waiting on a nameserver that never answers.
    """
    cached = _ADDRESS_CACHE.get(hostname)
    if cached is not None:
        address, when, resolves = cached
        if time.monotonic() - when <= _ADDRESS_TTL_SECONDS:
            return None if resolves else address

    if _resolver_answers(hostname):
        _ADDRESS_CACHE[hostname] = ("", time.monotonic(), True)
        return None

    address = _cached_address(hostname)
    if address is None:
        address = resolve_over_https(hostname)
        _remember_address(hostname, address)
    _ADDRESS_CACHE[hostname] = (address, time.monotonic(), False)
    return address


def doku_error_detail(res: httpx.Response) -> str:
    """A refusal, in words.

    DOKU puts the reason in the body — which field was wrong, or that the
    signature did not check out — and leaves the status code saying only that
    something was. The body is worth having: it is the difference between "HTTP
    400" and "invalid client id" when you are trying to work out why a
    checkout will not open.
    """
    try:
        error = res.json()["error"]
    except (KeyError, TypeError, ValueError):
        return f"HTTP {res.status_code}: {res.text[:200]}"

    parts = [f"HTTP {res.status_code}"]
    if isinstance(error, dict):
        for key in ("type", "code", "message"):
            value = error.get(key)
            if value:
                parts.append(f"{key}={value}")
        # Validation refusals name the offending fields, which is the useful bit.
        fields = error.get("fields") or error.get("field_errors")
        if fields:
            parts.append(f"fields={fields}")
    else:
        parts.append(str(error))
    return ", ".join(parts)


@dataclass
class CheckoutResult:
    invoice_number: str
    checkout_url: str
    token_id: str
    request_id: str = ""


def new_invoice_number() -> str:
    return "MAF-" + uuid7().hex.upper()[:20]


def create_checkout(
    *, invoice_number: str, amount: int, customer_name: str, callback_url: str = ""
) -> CheckoutResult:
    """Create a DOKU hosted checkout page (sandbox by default).

    Raises DokuError when keys are missing or DOKU rejects the request.
    """
    if not settings.doku_configured:
        raise DokuError("DOKU keys not configured (see docs/PAYMENTS.md)")
    if settings.doku_config_problem:
        raise DokuError(settings.doku_config_problem)
    body = {
        "order": {"invoice_number": invoice_number, "amount": amount},
        "payment": {"payment_due_date": 60},
        "customer": {"name": customer_name},
    }
    if callback_url:
        body["order"]["callback_url"] = callback_url
    raw = json.dumps(body, separators=(",", ":")).encode()
    timestamp = utc_timestamp()
    request_id = new_request_id()
    headers = {
        "Content-Type": "application/json",
        "Client-Id": settings.doku_client_id,
        "Request-Id": request_id,
        "Request-Timestamp": timestamp,
        "Signature": build_signature(
            client_id=settings.doku_client_id,
            request_id=request_id,
            timestamp=timestamp,
            request_target=CHECKOUT_TARGET,
            digest=build_digest(raw),
            secret=settings.doku_secret_key,
        ),
    }
    try:
        res = post_to_doku(
            settings.doku_base_url + CHECKOUT_TARGET,
            content=raw,
            headers=headers,
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise DokuError(f"DOKU request failed: {exc}") from exc
    if res.status_code != 200:
        # DOKU answers a refusal with the reason in the body: which field was
        # wrong, or that the signature did not match. The status code alone says
        # only that something was, which is no help at three in the morning.
        raise DokuError(f"DOKU rejected checkout: {doku_error_detail(res)}") from None
    try:
        payment = res.json()["response"]["payment"]
        return CheckoutResult(
            invoice_number=invoice_number,
            checkout_url=payment["url"],
            token_id=payment.get("token_id", ""),
            request_id=request_id,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DokuError("DOKU returned an unexpected body") from exc


REFUND_TARGET = "/cancellation/credit-card/refund"


@dataclass
class RefundResult:
    status: str  # SUCCESS | FAILED (as reported by DOKU)
    kind: str  # VOID | PARTIAL_REFUND | FULL_REFUND | MANUAL_* (may be empty)
    message: str
    approval_code: str = ""


def request_refund(
    *, invoice_number: str, original_request_id: str, amount: int
) -> RefundResult:
    """Ask DOKU to return money for a card payment.

    `original_request_id` is the Request-Id of the checkout that was paid — DOKU
    refuses a refund without it. Card channel only: the endpoint is documented for
    cards aggregator/direct, so a transfer or e-wallet payment has to be refunded
    from the DOKU dashboard instead (the service reports that as a failure).
    """
    if not settings.doku_configured:
        raise DokuError("DOKU keys not configured (see docs/PAYMENTS.md)")
    if settings.doku_config_problem:
        raise DokuError(settings.doku_config_problem)
    if not original_request_id:
        raise DokuError("the payment has no provider request id to refund against")
    body = {
        "order": {"invoice_number": invoice_number},
        "payment": {"original_request_id": original_request_id},
        "refund": {"amount": amount},
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    timestamp = utc_timestamp()
    request_id = new_request_id()
    headers = {
        "Content-Type": "application/json",
        "Client-Id": settings.doku_client_id,
        "Request-Id": request_id,
        "Request-Timestamp": timestamp,
        "Signature": build_signature(
            client_id=settings.doku_client_id,
            request_id=request_id,
            timestamp=timestamp,
            request_target=REFUND_TARGET,
            digest=build_digest(raw),
            secret=settings.doku_secret_key,
        ),
    }
    try:
        res = post_to_doku(
            settings.doku_base_url + REFUND_TARGET,
            content=raw,
            headers=headers,
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise DokuError(f"DOKU request failed: {exc}") from exc
    if res.status_code != 200:
        raise DokuError(f"DOKU rejected the refund: {doku_error_detail(res)}") from None
    try:
        refund = res.json()["response"]["refund"]
        return RefundResult(
            status=str(refund["status"]).upper(),
            kind=str(refund.get("type", "")),
            message=str(refund.get("message", "")),
            approval_code=str(refund.get("approval_code", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DokuError("DOKU returned an unexpected refund body") from exc
