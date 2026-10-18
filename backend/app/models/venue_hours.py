from datetime import time

from sqlalchemy import Boolean, ForeignKey, Integer, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class VenueHours(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """Opening hours for one weekday of a venue.

    `day_of_week` follows `datetime.date.weekday()`: 0 = Monday ... 6 = Sunday.
    Days without a row fall back to the default hours from settings, so slot
    generation always has a window and the manager UI always has 7 rows to edit.
    """

    __tablename__ = "venue_hours"
    __table_args__ = (
        UniqueConstraint("venue_id", "day_of_week", name="uq_venue_hours_venue_day"),
    )

    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    opens_at: Mapped[time] = mapped_column(Time, nullable=False)
    closes_at: Mapped[time] = mapped_column(Time, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
