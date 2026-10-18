from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class Notification(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """A message the venue owes a guest, written when a booking changes.

    The row is the queue entry, not the delivery: `transport` records how it left
    (log/smtp/whatsapp) and `status` says whether that counted as a real send.
    `logged` means the server only recorded it because no provider is set up.
    """

    __tablename__ = "notifications"

    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id"), nullable=True
    )
    group_public_id: Mapped[UUID | None] = mapped_column(nullable=True)
    event: Mapped[str] = mapped_column(String(24), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    recipient: Mapped[str] = mapped_column(String(160), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    transport: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    error: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
