from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class Court(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """A bookable facility inside a venue. Rates differ weekday vs weekend.

    A NULL rate means the manager has not priced that day, which takes the
    facility out of booking without deactivating it (see `kind` for the
    facility category shown in filters).
    """

    __tablename__ = "courts"
    # The API only knows padel, so the column says so too. Without this the
    # database could hold a sport the response schema refuses, and every
    # listing that included that court would come back a 500.
    __table_args__ = (CheckConstraint("sport = 'padel'", name="ck_courts_sport"),)

    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sport: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="court")
    price_weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_weekend: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Optional premium rate for a window of hours (peak time). Active only when
    # all three are set: it overlays the day's rate inside [start, end), so a
    # court can charge more for an evening without touching weekday/weekend.
    price_peak: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peak_start_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peak_end_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Photo of the facility itself (upload under /media or a pasted link).
    image_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
