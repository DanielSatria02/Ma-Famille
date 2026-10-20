from sqlalchemy import JSON, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class Venue(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """A padel club (manager-owned). Client key is `public_id` (UUIDv7).

    `tags` backs the client filters (area type, popular for, ...) and `lat`/`lng`
    place the venue on the map panel.
    """

    __tablename__ = "venues"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Public URL of the cover photo: an upload under /media, or a link the manager
    # pasted. Null means the client draws its own placeholder.
    image_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
