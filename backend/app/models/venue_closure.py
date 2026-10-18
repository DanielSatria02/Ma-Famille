from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class VenueClosure(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """A date range the venue is shut, independent of the weekly hours.

    Holidays, renovation, a private event: the weekly schedule says "open", this
    row says "not that week". Booking and slot generation both check it.
    """

    __tablename__ = "venue_closures"

    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False, default="")
