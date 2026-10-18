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
        # A key that is present but cannot sign is not a working gateway. Saying
        # it is configured would put a Pay button in front of a customer whose
        # every attempt then fails at the last step.
        payment_configured=settings.doku_configured and not settings.doku_config_problem,
        payment_problem=settings.doku_config_problem,
    )
