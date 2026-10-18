"""Venue closure dates: holidays, renovation, private events.

The weekly hours say when a venue is normally open; a closure row overrides them
for a date range. Slot generation skips those days and the booking guard refuses
them, so an existing schedule cannot be booked around a closed day.
"""

from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.court import Court
from app.models.slot import Slot
from app.models.venue import Venue
from app.models.venue_closure import VenueClosure
from app.schemas.venue_closure import VenueClosureCreate


def _entry(db: Session, closure: VenueClosure, venue: Venue) -> dict:
    return {
        "public_id": closure.public_id,
        "venue_public_id": venue.public_id,
        "starts_on": closure.starts_on,
        "ends_on": closure.ends_on,
        "days": (closure.ends_on - closure.starts_on).days + 1,
        "reason": closure.reason or "",
    }


def list_closures(db: Session, venue: Venue) -> list[dict]:
    stmt = (
        select(VenueClosure)
        .where(VenueClosure.venue_id == venue.id)
        .order_by(VenueClosure.starts_on)
    )
    return [_entry(db, row, venue) for row in db.scalars(stmt).all()]


def closure_on(db: Session, venue: Venue, day: date) -> VenueClosure | None:
    """The closure covering that day, if the venue is shut."""
    stmt = (
        select(VenueClosure)
        .where(VenueClosure.venue_id == venue.id)
        .where(VenueClosure.starts_on <= day, VenueClosure.ends_on >= day)
        .order_by(VenueClosure.starts_on)
    )
    return db.scalars(stmt).first()


def closed_day(db: Session, venue: Venue, day: date) -> str | None:
    """Reason the venue is shut that day, or None when it is open."""
    closure = closure_on(db, venue, day)
    if closure is None:
        return None
    return closure.reason or "venue closed"


def days_off(db: Session, venue: Venue, from_day: date, to_day: date) -> set[date]:
    """Every closed date in the window, expanded from the closure ranges."""
    stmt = (
        select(VenueClosure)
        .where(VenueClosure.venue_id == venue.id)
        .where(VenueClosure.starts_on <= to_day, VenueClosure.ends_on >= from_day)
    )
    closed: set[date] = set()
    for closure in db.scalars(stmt).all():
        day = max(closure.starts_on, from_day)
        last = min(closure.ends_on, to_day)
        while day <= last:
            closed.add(day)
            day = date.fromordinal(day.toordinal() + 1)
    return closed


def affected_bookings(db: Session, venue: Venue, starts_on: date, ends_on: date) -> int:
    """Active bookings already sitting inside that window."""
    stmt = (
        select(Booking)
        .join(Slot, Slot.id == Booking.slot_id)
        .join(Court, Court.id == Slot.court_id)
        .where(Court.venue_id == venue.id)
        .where(Booking.status != "cancelled")
        .where(
            Slot.starts_at >= datetime.combine(starts_on, time.min),
            Slot.starts_at <= datetime.combine(ends_on, time.max),
        )
    )
    return len(db.scalars(stmt).all())


def create_closure(db: Session, venue: Venue, data: VenueClosureCreate) -> dict:
    """Close a date range. Returns the closure plus the bookings it puts at risk."""
    closure = VenueClosure(
        venue_id=venue.id,
        starts_on=data.starts_on,
        ends_on=data.ends_on,
        reason=data.reason,
    )
    db.add(closure)
    db.commit()
    db.refresh(closure)
    entry = _entry(db, closure, venue)
    entry["affected_bookings"] = affected_bookings(
        db, venue, data.starts_on, data.ends_on
    )
    return entry


def delete_closure(db: Session, venue: Venue, public_id) -> bool:
    """Reopen the range. False when no such closure belongs to that venue."""
    closure = db.scalars(
        select(VenueClosure)
        .where(VenueClosure.public_id == public_id)
        .where(VenueClosure.venue_id == venue.id)
    ).first()
    if closure is None:
        return False
    db.delete(closure)
    db.commit()
    return True
