from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class Promotion(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """A discount code a customer can apply to a booking.

    Kind: percent (value 1–100, taken off the gross) or amount (value in rupiah,
    subtracted directly). `venue_id` nil means the code works anywhere; set, it
    is scoped to one venue. `max_uses` nil means unlimited; otherwise the code
    stops once `used_count` reaches it.

    Codes are stored upper-case so `HEMAT` and `hemat` are the same voucher.
    """

    __tablename__ = "promotions"

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="percent")
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Redemption window; either bound may be open.
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Scoped to one venue, or nil for any venue.
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), nullable=True)
