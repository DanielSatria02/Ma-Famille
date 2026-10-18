import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.ratelimit import throttle
from app.core.security import issue_session_token, manager_token_header, revoke_token
from app.db.session import get_db
from app.schemas.auth import (
    ManagerLoginRequest,
    ManagerLoginResponse,
    ManagerLogoutResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _caller(request: Request) -> str:
    """Best-effort identity for the lockout counter: the client's IP."""
    return request.client.host if request.client else "unknown"


@router.post(
    "/login",
    summary="Manager login, returns the token for X-Manager-Token",
    response_model=ManagerLoginResponse,
    responses={
        401: {"description": "Wrong password"},
        429: {"description": "Too many failed attempts"},
        501: {"description": "Manager login not configured"},
    },
)
def login(body: ManagerLoginRequest, request: Request) -> ManagerLoginResponse:
    if not settings.manager_password:
        raise HTTPException(status_code=501, detail="manager login is not configured")

    key = _caller(request)
    window_seconds = settings.manager_lockout_minutes * 60
    # Throttle before touching the password comparison, so a locked-out caller
    # cannot even measure how long a correct guess takes.
    if throttle.is_locked_out(key, settings.manager_lockout_attempts, window_seconds):
        retry_after = throttle.retry_after(key, window_seconds)
        raise HTTPException(
            status_code=429,
            detail="too many failed attempts, try again later",
            headers={"Retry-After": str(retry_after)},
        )

    if not hmac.compare_digest(body.password, settings.manager_password):
        throttle.record_failure(key)
        raise HTTPException(status_code=401, detail="wrong password")

    # A correct password wipes the slate so a typo streak never lingers.
    throttle.clear(key)
    token, expires_at = issue_session_token()
    return ManagerLoginResponse(token=token, expires_at=expires_at)


@router.post(
    "/logout",
    summary="Revoke the session token so it stops working (manager)",
    response_model=ManagerLogoutResponse,
    responses={501: {"description": "Manager login not configured"}},
)
def logout(
    token: str | None = Security(manager_token_header),
    db: Session = Depends(get_db),
) -> ManagerLogoutResponse:
    """Stop a session token before it expires.

    Tokens are stateless HMACs, so this writes the token's hash to a deny-list
    that every manager check consults. The static MANAGER_TOKEN is a shared
    secret, not a session — it cannot be revoked here.
    """
    if not settings.manager_password:
        raise HTTPException(status_code=501, detail="manager login is not configured")
    if not token:
        raise HTTPException(status_code=401, detail="manager token required")
    return ManagerLogoutResponse(revoked=revoke_token(db, token))
