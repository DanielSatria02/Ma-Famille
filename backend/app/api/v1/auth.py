import hmac

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.security import issue_session_token
from app.schemas.auth import ManagerLoginRequest, ManagerLoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    summary="Manager login, returns the token for X-Manager-Token",
    response_model=ManagerLoginResponse,
    responses={
        401: {"description": "Wrong password"},
        501: {"description": "Manager login not configured"},
    },
)
def login(body: ManagerLoginRequest) -> ManagerLoginResponse:
    if not settings.manager_password:
        raise HTTPException(status_code=501, detail="manager login is not configured")
    if not hmac.compare_digest(body.password, settings.manager_password):
        raise HTTPException(status_code=401, detail="wrong password")
    token, expires_at = issue_session_token()
    return ManagerLoginResponse(token=token, expires_at=expires_at)
