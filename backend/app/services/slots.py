from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.court import Court
from app.models.slot import Slot
from app.models.venue import Venue
from app.schemas.slot import SlotBlockRequest, SlotCreate, SlotGenerateRequest, SlotUpdate
from app.services import bookings as booking_service
from app.services import courts as court_service
from app.services import hours as hours_service


def _court_id(db: Session, court_public_id: UUID) -> int | None:
    court = db.scalars(select(Court).where(Court.public_id == court_public_id)).first()
    return court.id if court else None


def list_slots(db: Session, court_public_id: UUID, day: date) -> list[Slot] | None:
    court_id = _court_id(db, court_public_id)
    if court_id is None:
        return None
    booking_service.expire_stale_bookings(db, settings.booking_ttl_minutes)
    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)
    stmt = (
        select(Slot)
        .where(Slot.court_id == court_id)
        .where(Slot.starts_at >= start, Slot.ends_at <= end)
        .order_by(Slot.starts_at)
    )
    return list(db.scalars(stmt).all())


def get_by_public_id(db: Session, public_id: UUID) -> Slot | None:
    return db.scalars(select(Slot).where(Slot.public_id == public_id)).first()


def create_slots(db: Session, items: list[SlotCreate]) -> list[Slot] | None:
    court_ids: dict[UUID, int] = {}
    rows: list[Slot] = []
    for item in items:
        if item.court_public_id not in court_ids:
            court_id = _court_id(db, item.court_public_id)
            if court_id is None:
                return None
            court_ids[item.court_public_id] = court_id
        rows.append(
            Slot(
                court_id=court_ids[item.court_public_id],
                starts_at=item.starts_at,
                ends_at=item.ends_at,
                price=item.price,
            )
        )
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def update_slot(db: Session, slot: Slot, data: SlotUpdate) -> Slot:
    if data.status is not None:
        slot.status = data.status
    if data.price is not None:
        slot.price = data.price
    db.commit()
    db.refresh(slot)
    return slot


def _naive(value: datetime) -> datetime:
    """Postgres hands back tz-aware stamps; slot rows are stored as wall time."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _target_courts(db: Session, data: SlotGenerateRequest) -> list[Court] | None:
    if data.court_public_id is not None:
        court = db.scalars(
            select(Court).where(Court.public_id == data.court_public_id)
        ).first()
        return [court] if court is not None else None
    venue = db.scalars(
        select(Venue).where(Venue.public_id == data.venue_public_id)
    ).first()
    if venue is None:
        return None
    stmt = (
        select(Court)
        .where(Court.venue_id == venue.id, Court.is_active.is_(True))
        .order_by(Court.id)
    )
    return list(db.scalars(stmt).all())


def generate_slots(db: Session, data: SlotGenerateRequest) -> dict | None:
    """Create one slot per opening hour, per court, per day. Returns None when
    the court/venue id is unknown."""
    courts = _target_courts(db, data)
    if courts is None:
        return None
    booking_service.expire_stale_bookings(db, settings.booking_ttl_minutes)

    created = skipped_existing = skipped_closed_days = skipped_unpriced = 0
    day = data.from_day
    while day <= data.to_day:
        day_start = datetime.combine(day, time.min)
        day_end = datetime.combine(day, time.max)
        for court in courts:
            venue = db.get(Venue, court.venue_id)
            window = hours_service.window(db, venue, day.weekday())
            if window is None:
                skipped_closed_days += 1
                continue
            price = court_service.rate_for(court, day)
            if price is None:
                skipped_unpriced += 1
                continue
            opens_at, closes_at = window
            taken = {
                _naive(start)
                for start in db.scalars(
                    select(Slot.starts_at)
                    .where(Slot.court_id == court.id)
                    .where(Slot.starts_at >= day_start, Slot.starts_at <= day_end)
                ).all()
            }
            for hour in range(opens_at.hour, closes_at.hour):
                starts_at = datetime.combine(day, time(hour))
                if starts_at in taken:
                    skipped_existing += 1
                    continue
                db.add(
                    Slot(
                        court_id=court.id,
                        starts_at=starts_at,
                        ends_at=datetime.combine(day, time(hour + 1)),
                        price=price,
                    )
                )
                created += 1
        day += timedelta(days=1)

    if created:
        db.commit()
    return {
        "from_day": data.from_day,
        "to_day": data.to_day,
        "courts": len(courts),
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_closed_days": skipped_closed_days,
        "skipped_unpriced": skipped_unpriced,
    }


def block_window(db: Session, data: SlotBlockRequest) -> dict | None:
    """Close or reopen every hour of a window, per court. Returns None when the
    court/venue id is unknown.

    Booked and held hours are skipped: a manager cannot cancel somebody's game
    by closing the hours around it.
    """
    courts = _target_courts(db, data)
    if courts is None:
        return None
    booking_service.expire_stale_bookings(db, settings.booking_ttl_minutes)

    updated = unchanged = skipped_booked = skipped_missing = 0
    days = 0
    day = data.from_day
    while day <= data.to_day:
        days += 1
        day_start = datetime.combine(day, time.min)
        day_end = datetime.combine(day, time.max)
        for court in courts:
            rows = {
                _naive(slot.starts_at).hour: slot
                for slot in db.scalars(
                    select(Slot)
                    .where(Slot.court_id == court.id)
                    .where(Slot.starts_at >= day_start, Slot.starts_at <= day_end)
                ).all()
            }
            for hour in range(data.from_hour, data.to_hour):
                slot = rows.get(hour)
                if slot is None:
                    skipped_missing += 1
                elif slot.status in ("booked", "held"):
                    skipped_booked += 1
                elif slot.status == data.status:
                    unchanged += 1
                else:
                    slot.status = data.status
                    updated += 1
        day += timedelta(days=1)

    if updated:
        db.commit()
    return {
        "from_day": data.from_day,
        "to_day": data.to_day,
        "from_hour": data.from_hour,
        "to_hour": data.to_hour,
        "status": data.status,
        "courts": len(courts),
        "days": days,
        "updated": updated,
        "unchanged": unchanged,
        "skipped_booked": skipped_booked,
        "skipped_missing": skipped_missing,
    }


def court_public_id(db: Session, slot: Slot) -> UUID:
    return db.get(Court, slot.court_id).public_id
