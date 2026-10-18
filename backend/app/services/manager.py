from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.booking import Booking
from app.models.slot import Slot
from app.services import bookings as booking_service


def incoming_bookings(
    db: Session,
    booking_status: str | None = None,
    day: date | None = None,
    from_day: date | None = None,
    to_day: date | None = None,
    limit: int | None = None,
    offset: int = 0,
):
    """Bookings ordered by start time, optionally narrowed to a day or range."""
    stmt = _incoming_stmt(booking_status, day, from_day, to_day).order_by(
        Slot.starts_at, Booking.id
    )
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all())


def count_incoming(
    db: Session,
    booking_status: str | None = None,
    day: date | None = None,
    from_day: date | None = None,
    to_day: date | None = None,
) -> int:
    """How many rows `incoming_bookings` would return without the page slice."""
    stmt = select(func.count()).select_from(Slot).join(Booking, Booking.slot_id == Slot.id)
    stmt = _apply_filters(stmt, booking_status, day, from_day, to_day)
    return int(db.scalar(stmt) or 0)


def _incoming_stmt(booking_status, day, from_day, to_day):
    stmt = select(Booking).join(Slot, Slot.id == Booking.slot_id)
    return _apply_filters(stmt, booking_status, day, from_day, to_day)


def _apply_filters(stmt, booking_status, day, from_day, to_day):
    if booking_status is not None:
        stmt = stmt.where(Booking.status == booking_status)
    if day is not None:
        stmt = stmt.where(
            Slot.starts_at >= datetime.combine(day, time.min),
            Slot.starts_at <= datetime.combine(day, time.max),
        )
    else:
        if from_day is not None:
            stmt = stmt.where(Slot.starts_at >= datetime.combine(from_day, time.min))
        if to_day is not None:
            stmt = stmt.where(Slot.starts_at <= datetime.combine(to_day, time.max))
    return stmt


def occupancy(db: Session, from_day: date, to_day: date) -> list[dict]:
    points: list[dict] = []
    day = from_day
    while day <= to_day:
        start = datetime.combine(day, time.min)
        end = datetime.combine(day, time.max)
        total = db.scalar(
            select(func.count())
            .select_from(Slot)
            .where(Slot.starts_at >= start, Slot.starts_at <= end)
        )
        booked = db.scalar(
            select(func.count(func.distinct(Booking.slot_id)))
            .select_from(Booking)
            .join(Slot, Slot.id == Booking.slot_id)
            .where(
                Slot.starts_at >= start,
                Slot.starts_at <= end,
                Booking.status != "cancelled",
            )
        )
        points.append(
            {
                "day": day,
                "total_slots": total,
                "booked_slots": booked,
                "occupancy_rate": (booked / total) if total else 0.0,
            }
        )
        day += timedelta(days=1)
    return points


def _visit_count(db: Session, from_day: date, to_day: date, status: str | None) -> int:
    """Distinct booking groups touching [from_day, to_day]. Cancelled bookings
    count only when `status` asks for them, and every hour of one visit counts once."""
    start = datetime.combine(from_day, time.min)
    end = datetime.combine(to_day, time.max)
    group_id = func.coalesce(Booking.group_public_id, Booking.public_id)
    stmt = (
        select(func.count(func.distinct(group_id)))
        .select_from(Booking)
        .join(Slot, Slot.id == Booking.slot_id)
        .where(Slot.starts_at >= start, Slot.starts_at <= end)
    )
    stmt = (
        stmt.where(Booking.status != "cancelled")
        if status is None
        else stmt.where(Booking.status == status)
    )
    return db.scalar(stmt) or 0


def stats(db: Session, day: date, week_start: date | None = None) -> dict:
    booking_service.expire_stale_bookings(db, settings.booking_ttl_minutes)
    start = week_start if week_start is not None else day - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    return {
        "day": day,
        "week_start": start,
        "week_end": end,
        "todays_bookings": _visit_count(db, day, day, None),
        "weekly_visitors": _visit_count(db, start, end, None),
        "cancelled_bookings": _visit_count(db, start, end, "cancelled"),
    }
