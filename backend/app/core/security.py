"""Lightweight access control.

Manager routes accept either the static `MANAGER_TOKEN` (server-to-server,
local dev) or a session token from `POST /auth/login`: an HMAC-signed
`manager:<expires_at>` payload signed with the manager password.

Nothing configured leaves routes open, which is the local-dev default.
Production sets MANAGER_TOKEN and/or MANAGER_PASSWORD.

Session tokens are stateless, so `POST /auth/logout` cannot un-sign one — it
writes the token's hash to a deny-list instead, and every check consults that
list. Only the hash is stored, so a leaked table cannot be replayed as live
tokens. The static `MANAGER_TOKEN` is a shared secret, not a session, and is
deliberately not revocable this way.
"""

import base64
import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.revoked_token import RevokedToken

_scheme = manager_token_header = APIKeyHeader(name="X-Manager-Token", auto_error=False)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return _b64(digest)


def _secret() -> str:
    return settings.manager_password or settings.manager_token


def token_hash(token: str) -> str:
    """SHA-256 of a token — what the deny-list stores, never the token itself."""
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session_token() -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.manager_session_minutes)
    # A random nonce makes each login a distinct token. Without it the payload is
    # just `manager:<expiry>`, so two logins in the same second are byte-identical
    # — and logging out one "device" would silently revoke the other.
    payload = f"manager:{int(expires_at.timestamp())}:{secrets.token_hex(8)}"
    return f"{_b64(payload.encode())}.{_sign(payload, _secret())}", expires_at


def _parse_session_token(token: str) -> int | None:
    """Signature-check a session token; return its expiry (epoch seconds) or None."""
    if not _secret() or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(signature, _sign(payload, _secret())):
        return None
    role, sep, rest = payload.partition(":")
    if role != "manager" or not sep:
        return None
    # `manager:<expiry>:<nonce>` — the nonce is what makes each login distinct.
    # A bare `manager:<expiry>` is refused: two of those minted in the same
    # second are byte-identical, which would make per-device logout revoke the
    # wrong session.
    expires_at, sep, nonce = rest.partition(":")
    if not expires_at.isdigit() or not sep or not nonce:
        return None
    return int(expires_at)


def verify_session_token(token: str) -> bool:
    expires_at = _parse_session_token(token)
    if expires_at is None:
        return False
    return expires_at > int(time.time())


def is_token_revoked(db: Session, token: str) -> bool:
    """Has this session token been logged out?"""
    row = db.scalar(
        select(RevokedToken.id).where(RevokedToken.token_hash == token_hash(token))
    )
    return row is not None


def revoke_token(db: Session, token: str) -> bool:
    """Deny-list a session token (logout). Idempotent.

    Returns True when this call is what revoked it. An invalid or already-expired
    token is not worth a row, so it returns False and writes nothing.
    """
    expires_at = _parse_session_token(token)
    if expires_at is None or expires_at <= int(time.time()):
        return False
    hashed = token_hash(token)
    if is_token_revoked(db, token):
        return False
    db.add(
        RevokedToken(
            token_hash=hashed,
            expires_at=datetime.fromtimestamp(expires_at, UTC),
        )
    )
    # Anything already past expiry can never match again — drop it while here.
    db.execute(delete(RevokedToken).where(RevokedToken.expires_at < datetime.now(UTC)))
    db.commit()
    return True


def is_manager(token: str | None, db: Session | None = None) -> bool:
    """May this caller act as the manager?

    True when nothing is configured (local dev), when the token matches the
    static `MANAGER_TOKEN`, or when it is a valid, non-revoked session token.
    Revocation is only consulted when a session is handed in — the static token
    is a shared secret with nothing to revoke.
    """
    if not settings.manager_token and not settings.manager_password:
        return True
    if not token:
        return False
    if settings.manager_token and hmac.compare_digest(token, settings.manager_token):
        return True
    if not verify_session_token(token):
        return False
    if db is not None and is_token_revoked(db, token):
        return False
    return True


def require_manager(
    token: str | None = Security(_scheme),
    db: Session = Depends(get_db),
) -> None:
    if is_manager(token, db=db):
        return
    raise HTTPException(status_code=401, detail="manager token required")
