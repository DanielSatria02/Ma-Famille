from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ — so uploads land in the same place whether the server is started from
# the repo root or from backend/, and whether tests run from either.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ma-famille-api"
    app_env: str = "development"
    api_v1_prefix: str = "/v1"
    backend_cors_origins: str = "http://localhost:5173,http://localhost:3000"
    database_url: str = "postgresql+psycopg://mafamille:mafamille@localhost:5432/mafamille"
    # Subpath hosting: "/ma-famille" in prod (college.rzidinc.com/ma-famille),
    # "" for local dev. FastAPI strips this prefix before routing and uses it
    # when generating /docs and /openapi.json URLs.
    root_path: str = ""
    doku_client_id: str = ""
    doku_secret_key: str = ""
    doku_base_url: str = "https://api-sandbox.doku.com"
    # Empty = open (local dev). Production sets this in backend/.env.
    manager_token: str = ""
    # Login password for the manager dashboard. Empty = POST /auth/login 501.
    manager_password: str = ""
    # Lifetime of a session token issued by POST /auth/login.
    manager_session_minutes: int = 480
    # Wrong passwords allowed from one caller before the login is locked out.
    manager_lockout_attempts: int = 5
    # How long that lockout lasts, and how far back failures are counted.
    manager_lockout_minutes: int = 15
    # Pending bookings older than this are auto-cancelled on next read/write.
    booking_ttl_minutes: int = 30
    # Minimum days ahead a client may book (0 = today allowed, prod sets 1).
    booking_min_lead_days: int = 0
    # Opening window used for days a venue has no stored hours for.
    default_opens_at: str = "08:00"
    default_closes_at: str = "22:00"
    # Where uploaded venue/court photos live, and the URL they are served from.
    media_root: str = str(BACKEND_ROOT / "media")
    media_url: str = "/media"
    max_photo_bytes: int = 500_000
    # Guest notifications. `notify_transport` picks how a queued message leaves
    # the building: "log" (default: recorded in the DB + server log, nothing is
    # delivered), "smtp" for email, "whatsapp" for the Cloud API.
    notify_transport: str = "log"
    notify_from: str = "no-reply@ma-famille.local"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def doku_configured(self) -> bool:
        return bool(self.doku_client_id and self.doku_secret_key)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host)

    @property
    def whatsapp_configured(self) -> bool:
        return bool(self.whatsapp_token and self.whatsapp_phone_id)


settings = Settings()
