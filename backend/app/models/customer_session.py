from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class CustomerSession(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """A signed-in customer session.

    The token is opaque random bytes; only its SHA-256 is stored, so a leaked
    table cannot be replayed as a live login. Kept as a row rather than a
    stateless HMAC (which is what the manager uses) because a customer secret
    has nowhere to live in local dev, where `MANAGER_PASSWORD` is unset —
    and because logging out has to actually end the session.
    """

    __tablename__ = "customer_sessions"

    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    # SHA-256 of the token handed to the client — never the token itself.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Best-effort identity for rate limiting, same idea as the manager lockout.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
