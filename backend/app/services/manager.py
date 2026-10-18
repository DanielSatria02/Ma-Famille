from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.slot import Slot


def incoming_bookings(
    db: Session,
    booking_status: str | None = None,
    day: date | None = None,
    from_day: date | None = None,
    to_day: date | None = None,
):
    """Bookings ordered by start time, optionally narrowed to a day or range."""
    stmt = (
        select(Booking)
        .join(Slot, Slot.id == Booking.slot_id)
        .order_by(Slot.starts_at, Booking.id)
    )
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
    return list(db.scalars(stmt).all())


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
