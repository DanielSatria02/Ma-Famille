from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin


class RevokedToken(Base, PKMixin, PublicIdMixin):
    """A session token the manager has logged out — it must stop working now.

    Session tokens are stateless HMACs, so revocation needs a deny-list. Only the
    SHA-256 hash is stored: a leaked database dump must not hand out live tokens.
    `expires_at` is copied from the token so the row can be garbage-collected once
    the token would have died anyway.
    """

    __tablename__ = "revoked_tokens"

    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
