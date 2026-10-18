from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class Booking(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """A customer booking on a slot.

    Status: pending | confirmed | cancelled. Only one non-cancelled booking
    may exist per slot — enforced by a partial unique index, so the conflict
    guard holds even under race conditions.

    One booking covers one slot, so a multi-hour booking is several rows
    sharing `group_public_id`: that is the unit a client books and cancels.
    """

    __tablename__ = "bookings"
    __table_args__ = (
        Index(
            "ix_bookings_slot_active",
            "slot_id",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
            sqlite_where=text("status <> 'cancelled'"),
        ),
    )

    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"), nullable=False)
    group_public_id: Mapped[UUID | None] = mapped_column(
        Uuid, index=True, nullable=True
    )
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_contact: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
