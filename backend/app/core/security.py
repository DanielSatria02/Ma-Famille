"""Lightweight access control.

Manager routes accept either the static `MANAGER_TOKEN` (server-to-server,
local dev) or a session token from `POST /auth/login`: an HMAC-signed
`manager:<expires_at>` payload signed with the manager password.

Nothing configured leaves routes open, which is the local-dev default.
Production sets MANAGER_TOKEN and/or MANAGER_PASSWORD.
"""

import base64
import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.core.config import settings

_scheme = manager_token_header = APIKeyHeader(name="X-Manager-Token", auto_error=False)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return _b64(digest)


def _secret() -> str:
    return settings.manager_password or settings.manager_token


def issue_session_token() -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.manager_session_minutes)
    payload = f"manager:{int(expires_at.timestamp())}"
    return f"{_b64(payload.encode())}.{_sign(payload, _secret())}", expires_at


def verify_session_token(token: str) -> bool:
    secret = _secret()
    if not secret or "." not in token:
        return False
    encoded, signature = token.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return False
    if not hmac.compare_digest(signature, _sign(payload, secret)):
        return False
    role, _, expires_at = payload.partition(":")
    if role != "manager" or not expires_at.isdigit():
        return False
    return int(expires_at) > int(time.time())


def is_manager(token: str | None) -> bool:
    """May this caller act as the manager?

    True when nothing is configured (local dev), when the token matches the
    static `MANAGER_TOKEN`, or when it is a valid session token.
    """
    if not settings.manager_token and not settings.manager_password:
        return True
    if not token:
        return False
    if settings.manager_token and hmac.compare_digest(token, settings.manager_token):
        return True
    return verify_session_token(token)


def require_manager(token: str | None = Security(_scheme)) -> None:
    if is_manager(token):
        return
    raise HTTPException(status_code=401, detail="manager token required")
