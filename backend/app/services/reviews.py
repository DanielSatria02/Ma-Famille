"""Leaving a rating, and reading what other visitors thought.

The rule that shapes this module: a rating has to be earned by a visit. A
review is only accepted when the caller has a booking at that venue whose
slot has already started and which was not cancelled, so nobody can rate a
place they never played at, and nobody can pad an average with a second
account before their first visit even happens.

A signed-in customer is held to one review per venue, updated in place on a
re-submit — which is what people expect from a rating form, and what keeps
the average from being padded by repeated submits. A visitor without an
account is held by the contact they booked with, for the same reason.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.booking import Booking
from app.models.court import Court
from app.models.customer import Customer
from app.models.review import Review
from app.models.slot import Slot
from app.models.venue import Venue
from app.services.bookings import normalise_contact


class ReviewError(Exception):
    """A rule about reviews was broken. The API turns this into a 4xx."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _digits(value: str) -> str:
    """The comparable form of a contact: digits, without `0` or `+62`.

    The booking routes already settled how two spellings of one number are
    recognised, so reviews use the same function rather than a second opinion:
    a reviewer who writes `+62 812…` for a visit booked as `0812…` is updating
    their own rating, not opening a second account of it.
    """
    return normalise_contact(value)


def _author_name(review: Review, customer: Customer | None) -> str:
    if customer is not None:
        return customer.display_name or customer.email
    return review.customer_contact


def author_name(review: Review) -> str:
    """How the venue shows this reviewer: their name with an account, else the
    contact the visit was booked with."""
    return _author_name(review, review.customer)


def _completed_visit(
    db: Session, venue_id: int, customer_id: int | None, contact: str
) -> Booking | None:
    """The booking that earns this rating, or None.

    "Earned" means the visit has already begun — a booking for next Friday is
    not an opinion yet — and was not cancelled.
    """
    started = db.scalars(
        select(Booking)
        .join(Slot, Slot.id == Booking.slot_id)
        .join(Court, Court.id == Slot.court_id)
        .where(
            Booking.status == "confirmed",
            Court.venue_id == venue_id,
            Slot.starts_at <= datetime.now(UTC),
        )
        .order_by(Slot.starts_at.desc())
    ).all()
    for booking in started:
        # With an account the account is the claim; without one, the contact.
        if customer_id is not None and booking.customer_id == customer_id:
            return booking
        if booking.customer_contact and _digits(booking.customer_contact) == _digits(contact):
            return booking
    return None


def _existing(db: Session, venue_id: int, customer_id: int | None, contact: str) -> Review | None:
    if customer_id is not None:
        by_account = db.scalars(
            select(Review).where(
                Review.venue_id == venue_id, Review.customer_id == customer_id
            )
        ).first()
        if by_account is not None:
            return by_account
    # Compared the same digit-wise way the visit was, so a second rating under a
    # differently written number updates the first one instead of adding a row.
    for review in db.scalars(
        select(Review).where(Review.venue_id == venue_id)
    ).all():
        if _digits(review.customer_contact) == _digits(contact):
            return review
    return None


def write_review(
    db: Session,
    *,
    venue_public_id,
    rating: int,
    comment: str | None,
    customer: Customer | None,
    customer_contact: str,
) -> tuple[Review, bool]:
    """Rate a venue, or replace the caller's earlier rating of it.

    Returns `(review, created)`. The caller needs to know which it was to
    answer 201 or 200, and it cannot tell from the timestamps: an update that
    lands in the same microsecond as the insert looks like a fresh row.

    Raises ReviewError with a 404 for an unknown venue, a 403 when the caller
    has no visit to speak from, and a 422 for a rating outside 1–5 (the schema
    enforces that last one too; it is repeated here so the service is safe on
    its own).
    """
    if not 1 <= rating <= 5:
        raise ReviewError("rating must be between 1 and 5")

    contact = customer_contact.strip()
    if not contact:
        raise ReviewError("a rating needs the contact the visit was booked with", 400)

    venue = db.scalars(select(Venue).where(Venue.public_id == venue_public_id)).first()
    if venue is None:
        raise ReviewError("no such venue", 404)

    customer_id = customer.id if customer is not None else None
    visit = _completed_visit(db, venue.id, customer_id, contact)
    if visit is None:
        raise ReviewError(
            "only a customer who has already played here can rate it", 403
        )

    existing = _existing(db, venue.id, customer_id, contact)
    if existing is not None:
        # Same reviewer, same venue: the newer opinion replaces the older one.
        existing.rating = rating
        existing.comment = comment
        db.commit()
        db.refresh(existing)
        return existing, False

    review = Review(
        venue_id=venue.id,
        customer_id=customer_id,
        customer_contact=contact,
        booking_group_public_id=str(visit.group_public_id) if visit.group_public_id else None,
        rating=rating,
        comment=comment,
    )
    db.add(review)
    try:
        db.commit()
    except IntegrityError:
        # Two tabs submitting at once: the unique constraint is the only thing
        # that can settle it, and it settles it in favour of the first write.
        db.rollback()
        existing = _existing(db, venue.id, customer_id, contact)
        if existing is None:
            raise ReviewError("could not save that rating, try again", 409) from None
        existing.rating = rating
        existing.comment = comment
        db.commit()
        db.refresh(existing)
        return existing, False
    db.refresh(review)
    return review, True


def list_reviews(db: Session, venue_public_id, *, limit: int = 20, offset: int = 0):
    """Newest first, with the writer's name resolved for display."""
    venue = db.scalars(select(Venue).where(Venue.public_id == venue_public_id)).first()
    if venue is None:
        raise ReviewError("no such venue", 404)
    rows = db.scalars(
        select(Review)
        .options(joinedload(Review.customer))
        .where(Review.venue_id == venue.id)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return venue, rows


def count_reviews(db: Session, venue_id: int) -> int:
    return db.scalar(select(func.count(Review.id)).where(Review.venue_id == venue_id)) or 0


def rating_summary(db: Session, venue_public_id):
    """Average, count and a per-star breakdown — what a venue page leads with."""
    venue = db.scalars(select(Venue).where(Venue.public_id == venue_public_id)).first()
    if venue is None:
        raise ReviewError("no such venue", 404)
    ratings = db.scalars(select(Review.rating).where(Review.venue_id == venue.id)).all()
    distribution = {str(star): 0 for star in range(5, 0, -1)}
    for value in ratings:
        distribution[str(value)] += 1
    average = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
    return venue, average, len(ratings), distribution
