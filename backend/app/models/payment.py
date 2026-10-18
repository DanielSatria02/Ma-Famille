from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class Payment(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """A deposit or full payment for a booking.

    Kind: deposit | full. Status: unpaid | paid | failed | refunded.
    No real gateway — DOKU sandbox drives transitions (see docs/PAYMENTS.md).
    """

    __tablename__ = "payments"

    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="deposit")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unpaid")
    invoice_number: Mapped[str | None] = mapped_column(
        String(60), nullable=True, unique=True
    )
    # Request-Id we sent DOKU when the checkout was created: a refund has to quote it.
    provider_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Whatever the gateway last said (RAW status), kept even when it changes nothing.
    provider_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Why a payment is not going through, in words a manager can read.
    failure_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
