"""Price quotes for a booking range.

A slot row's own price wins (it was priced when generated); hours without a
row fall back to the court's rate for that weekday. Nothing is written here,
so the quote is safe to call while the client is still picking a time.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.court import Court
from app.models.slot import Slot
from app.services import courts as court_service


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def range_hours(starts_at: datetime, ends_at: datetime) -> list[datetime]:
    count = int((ends_at - starts_at).total_seconds() // 3600)
    return [starts_at + timedelta(hours=offset) for offset in range(count)]


def _rows_of_day(db: Session, court: Court, day: date) -> dict[datetime, Slot]:
    stmt = (
        select(Slot)
        .where(Slot.court_id == court.id)
        .where(
            Slot.starts_at >= datetime.combine(day, time.min),
            Slot.ends_at <= datetime.combine(day, time.max),
        )
    )
    return {_naive(slot.starts_at): slot for slot in db.scalars(stmt).all()}


def quote(db: Session, court: Court, starts_at: datetime, ends_at: datetime) -> dict:
    rows = _rows_of_day(db, court, starts_at.date())

    unpriced = False
    breakdown: list[dict] = []
    for hour in range_hours(starts_at, ends_at):
        slot = rows.get(hour)
        if slot is not None:
            price = slot.price
        else:
            # Fallback is per hour, not per day: a peak hour with no slot row
            # (e.g. the window widened past what was generated) still pays peak.
            fallback_rate = court_service.rate_for_hour(court, starts_at.date(), hour.hour)
            if fallback_rate is not None:
                price = fallback_rate
            else:
                price = 0
                unpriced = True
        breakdown.append(
            {
                "hour": hour.hour,
                "starts_at": hour,
                "price": price,
                "slot_public_id": slot.public_id if slot is not None else None,
                "status": slot.status if slot is not None else None,
            }
        )

    free = all(entry["status"] in (None, "available") for entry in breakdown)
    return {
        "court_public_id": court.public_id,
        "court_name": court.name,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "hours": len(breakdown),
        "hourly_rate": breakdown[0]["price"] if breakdown else 0,
        "total": sum(entry["price"] for entry in breakdown),
        "is_bookable": court.is_active and free and not unpriced,
        "breakdown": breakdown,
    }
