from datetime import datetime

from pydantic import BaseModel, Field


class ManagerLoginRequest(BaseModel):
    """The login form posts email + password; only the password is checked
    while there is a single manager account."""

    password: str = Field(min_length=1, max_length=200)
    email: str | None = None


class ManagerLoginResponse(BaseModel):
    token: str
    token_type: str = "manager"
    role: str = "manager"
    expires_at: datetime


class ManagerLogoutResponse(BaseModel):
    """`revoked` is False when the token was already invalid, expired, or
    logged out before — logout is idempotent, not an error."""

    revoked: bool
