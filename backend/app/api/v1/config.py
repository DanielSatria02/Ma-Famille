from fastapi import APIRouter

from app.core.config import settings
from app.schemas.config import ClientConfig

router = APIRouter(prefix="/config", tags=["config"])


@router.get(
    "",
    summary="Client-facing settings (TTL, login and payment availability)",
    response_model=ClientConfig,
)
def client_config() -> ClientConfig:
    return ClientConfig(
        booking_ttl_minutes=settings.booking_ttl_minutes,
        booking_min_lead_days=settings.booking_min_lead_days,
        manager_login_enabled=bool(settings.manager_password),
        payment_configured=settings.doku_configured,
    )
