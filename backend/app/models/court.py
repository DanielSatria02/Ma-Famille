from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class Court(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """A bookable facility inside a venue. Rates differ weekday vs weekend.

    A NULL rate means the manager has not priced that day, which takes the
    facility out of booking without deactivating it (see `kind` for the
    facility category shown in filters).
    """

    __tablename__ = "courts"

    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sport: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="court")
    price_weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_weekend: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Photo of the facility itself (upload under /media or a pasted link).
    image_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
