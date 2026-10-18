"""Availability read models.

Both endpoints answer "what can a client book?", one day at a time or as a
per-day roll-up for a calendar. Slot rows stay the source of truth: an hour
without a row is reported as `unavailable` rather than silently dropped.
"""

from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.court import Court
from app.models.slot import Slot
from app.models.venue import Venue
from app.services import bookings as booking_service
from app.services import closures as closure_service
from app.services import hours as hours_service

# Slots are stored as wall time; Postgres returns them tz-aware.
_FREE_STATUSES = {"available"}


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _slots_of_day(db: Session, court: Court, day: date) -> list[Slot]:
    stmt = (
        select(Slot)
        .where(Slot.court_id == court.id)
        .where(
            Slot.starts_at >= datetime.combine(day, time.min),
            Slot.ends_at <= datetime.combine(day, time.max),
        )
        .order_by(Slot.starts_at)
    )
    return list(db.scalars(stmt).all())


def day_hours(db: Session, court: Court, day: date) -> dict:
    booking_service.expire_stale_bookings(db, settings.booking_ttl_minutes)
    venue = db.get(Venue, court.venue_id)
    # A closure (holiday) closes the whole date, whatever the weekly hours say.
    closure_reason = closure_service.closed_day(db, venue, day)
    entry = hours_service.day_hours(db, venue, day.weekday())
    window = None if closure_reason else hours_service.window(db, venue, day.weekday())

    rows = {_naive(slot.starts_at).hour: slot for slot in _slots_of_day(db, court, day)}
    hours: list[dict] = []
    if window is not None:
        opens_at, closes_at = window
        for hour in range(opens_at.hour, closes_at.hour):
            slot = rows.get(hour)
            hours.append(
                {
                    "hour": hour,
                    "starts_at": slot.starts_at if slot is not None else None,
                    "status": slot.status if slot is not None else "unavailable",
                    "price": slot.price if slot is not None else None,
                    "slot_public_id": slot.public_id if slot is not None else None,
                }
            )

    return {
        "court_public_id": court.public_id,
        "day": day,
        "day_of_week": day.weekday(),
        "is_closed": window is None,
        "closure_reason": closure_reason,
        "opens_at": None if window is None else entry["opens_at"],
        "closes_at": None if window is None else entry["closes_at"],
        "hours": hours,
    }


def date_summary(db: Session, court: Court, from_day: date, to_day: date) -> list[dict]:
    """One entry per day that has slots. Closed or ungenerated days are
    omitted: the calendar only needs days worth showing."""
    booking_service.expire_stale_bookings(db, settings.booking_ttl_minutes)
    stmt = (
        select(Slot)
        .where(Slot.court_id == court.id)
        .where(
            Slot.starts_at >= datetime.combine(from_day, time.min),
            Slot.starts_at <= datetime.combine(to_day, time.max),
        )
        .order_by(Slot.starts_at)
    )
    buckets: dict[date, list[Slot]] = {}
    for slot in db.scalars(stmt).all():
        buckets.setdefault(_naive(slot.starts_at).date(), []).append(slot)

    summary: list[dict] = []
    closed = closure_service.days_off(db, db.get(Venue, court.venue_id), from_day, to_day)
    for day, slots in buckets.items():
        if day in closed:
            # A holiday: the calendar must not offer a day the venue is shut.
            continue
        free = sum(1 for slot in slots if slot.status in _FREE_STATUSES)
        summary.append(
            {
                "day": day,
                "total_hours": len(slots),
                "booked_hours": len(slots) - free,
                "free_hours": free,
            }
        )
    return summary


def bookable_hours(db: Session, court: Court, day: date) -> set[int]:
    """Hours a client may still start a booking in (used by the booking guard)."""
    return {
        entry["hour"]
        for entry in day_hours(db, court, day)["hours"]
        if entry["status"] in _FREE_STATUSES
    }
