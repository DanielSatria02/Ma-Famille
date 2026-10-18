from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.venue import Venue


class Review(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """One customer's opinion of one venue.

    Gated on a real visit: a review can only be written by a customer whose
    booking at that venue is neither pending nor cancelled, so a rating is
    something that was earned by playing there rather than typed in. Before
    this existed a venue carried no reputation at all, and a group member had
    to ask around to know whether a court was worth booking.

    One row per customer per venue — writing again updates the earlier
    opinion, which is the behaviour people expect from a rating form and keeps
    the average from being padded by repeated submits.
    """

    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("customer_id", "venue_id", name="uq_reviews_customer_venue"),
    )

    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False, index=True)
    # Nullable like bookings: a visitor can rate without an account, keyed by
    # the contact they booked with. With an account the row moves with them.
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    # The contact the visit was booked with, so a walk-up visitor is still
    # held to one review and cannot pad the average from a fresh phone number.
    customer_contact: Mapped[str] = mapped_column(String(60), nullable=False)
    # The booking that earns the right to review; kept so the gate cannot be
    # satisfied by a later, unrelated booking.
    booking_group_public_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Resolved for display: a signed-in reviewer shows their name, a walk-up
    # one falls back to the contact they booked with.
    customer: Mapped[Customer | None] = relationship()
    venue: Mapped[Venue] = relationship()
