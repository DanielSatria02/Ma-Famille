"""Opening hours per weekday.

A venue only stores rows for days the manager changed; everything else falls
back to the default window from settings. Slot generation and booking
validation both read hours through here, so there is one answer per day.
"""

from datetime import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.venue import Venue
from app.models.venue_hours import VenueHours
from app.schemas.venue_hours import VenueHoursUpdate

WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def _default_entry(day_of_week: int) -> dict:
    return {
        "day_of_week": day_of_week,
        "day": WEEKDAY_NAMES[day_of_week],
        "opens_at": settings.default_opens_at,
        "closes_at": settings.default_closes_at,
        "is_closed": False,
        "is_default": True,
    }


def _entry(row: VenueHours) -> dict:
    return {
        "day_of_week": row.day_of_week,
        "day": WEEKDAY_NAMES[row.day_of_week],
        "opens_at": row.opens_at.strftime("%H:%M"),
        "closes_at": row.closes_at.strftime("%H:%M"),
        "is_closed": row.is_closed,
        "is_default": False,
    }


def _rows(db: Session, venue_id: int) -> dict[int, VenueHours]:
    stmt = select(VenueHours).where(VenueHours.venue_id == venue_id)
    return {row.day_of_week: row for row in db.scalars(stmt).all()}


def list_hours(db: Session, venue: Venue) -> list[dict]:
    """All 7 days, stored rows first and defaults for the rest."""
    rows = _rows(db, venue.id)
    return [
        _entry(rows[day]) if day in rows else _default_entry(day) for day in range(7)
    ]


def day_hours(db: Session, venue: Venue, day_of_week: int) -> dict:
    row = _rows(db, venue.id).get(day_of_week)
    return _entry(row) if row is not None else _default_entry(day_of_week)


def window(db: Session, venue: Venue, day_of_week: int) -> tuple[time, time] | None:
    """Open/close times to generate slots from, or None when closed that day."""
    entry = day_hours(db, venue, day_of_week)
    if entry["is_closed"]:
        return None
    return (
        time.fromisoformat(entry["opens_at"]),
        time.fromisoformat(entry["closes_at"]),
    )


def upsert_hours(
    db: Session, venue: Venue, day_of_week: int, data: VenueHoursUpdate
) -> dict:
    row = _rows(db, venue.id).get(day_of_week)
    if row is None:
        row = VenueHours(
            venue_id=venue.id,
            day_of_week=day_of_week,
            opens_at=time.fromisoformat(data.opens_at),
            closes_at=time.fromisoformat(data.closes_at),
            is_closed=data.is_closed,
        )
        db.add(row)
    else:
        row.opens_at = time.fromisoformat(data.opens_at)
        row.closes_at = time.fromisoformat(data.closes_at)
        row.is_closed = data.is_closed
    db.commit()
    db.refresh(row)
    return _entry(row)


def venue_public_id_of(db: Session, hours: VenueHours) -> UUID:
    return db.get(Venue, hours.venue_id).public_id
