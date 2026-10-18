from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.ids import uuid7
from app.models.booking import Booking
from app.models.court import Court
from app.models.payment import Payment
from app.models.slot import Slot
from app.models.venue import Venue
from app.schemas.booking import BookingCreate, BookingRangeCreate


class SlotUnavailable(RuntimeError):
    pass


class LeadTimeViolation(RuntimeError):
    pass


def expire_stale_bookings(db: Session, ttl_minutes: int) -> int:
    """Cancel pending bookings older than TTL and free their slots.

    Runs lazily inside read/write paths (no cron needed). Compares in
    Python so SQLite and Postgres timestamp flavors both behave.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    stale = db.scalars(select(Booking).where(Booking.status == "pending")).all()
    expired = 0
    for booking in stale:
        created = booking.created_at
        if created.tzinfo is not None:
            created = created.replace(tzinfo=None)
        if now - created > timedelta(minutes=ttl_minutes):
            booking.status = "cancelled"
            slot = db.get(Slot, booking.slot_id)
            if slot is not None and slot.status == "booked":
                slot.status = "available"
            expired += 1
    if expired:
        db.commit()
    return expired


def get_by_public_id(db: Session, public_id: UUID) -> Booking | None:
    return db.scalars(select(Booking).where(Booking.public_id == public_id)).first()


def list_by_contact(db: Session, customer_contact: str) -> list[Booking]:
    stmt = (
        select(Booking)
        .where(Booking.customer_contact == customer_contact)
        .order_by(Booking.id)
    )
    return list(db.scalars(stmt).all())


def create_booking(db: Session, data: BookingCreate) -> Booking | None:
    """Returns None when the slot is unknown; raises IntegrityError on conflict."""
    slot = db.scalars(select(Slot).where(Slot.public_id == data.slot_public_id)).first()
    if slot is None:
        return None
    expire_stale_bookings(db, settings.booking_ttl_minutes)
    db.refresh(slot)
    if slot.status != "available":
        raise SlotUnavailable(f"slot is {slot.status}")
    booking = Booking(
        slot_id=slot.id,
        group_public_id=uuid7(),
        customer_name=data.customer_name,
        customer_contact=data.customer_contact,
    )
    slot.status = "booked"
    db.add(booking)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(booking)
    return booking


def _naive(value: datetime) -> datetime:
    """Slots are stored as wall time; Postgres returns them tz-aware."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _check_lead_time(starts_at: datetime) -> None:
    lead_days = settings.booking_min_lead_days
    if lead_days <= 0:
        return
    earliest = datetime.now(UTC).date() + timedelta(days=lead_days)
    if starts_at.date() < earliest:
        raise LeadTimeViolation(
            f"bookings must be made at least {lead_days} day(s) in advance"
        )


def _group_slots(db: Session, court: Court, data: BookingRangeCreate) -> list[Slot]:
    """Slots for every hour of the range, or SlotUnavailable naming the hour."""
    day_start = datetime.combine(data.starts_at.date(), time.min)
    day_end = datetime.combine(data.starts_at.date(), time.max)
    rows = {
        _naive(slot.starts_at): slot
        for slot in db.scalars(
            select(Slot)
            .where(Slot.court_id == court.id)
            .where(Slot.starts_at >= day_start, Slot.starts_at <= day_end)
        ).all()
    }
    chosen: list[Slot] = []
    for offset in range(int((data.ends_at - data.starts_at).total_seconds() // 3600)):
        hour = data.starts_at + timedelta(hours=offset)
        slot = rows.get(hour)
        if slot is None:
            raise SlotUnavailable(f"no slot for {hour:%H:%M}")
        if slot.status != "available":
            raise SlotUnavailable(f"slot at {hour:%H:%M} is {slot.status}")
        chosen.append(slot)
    return chosen


def create_range_booking(db: Session, data: BookingRangeCreate) -> dict | None:
    """Book consecutive hours as one group. None when the court is unknown."""
    court = db.scalars(
        select(Court).where(Court.public_id == data.court_public_id)
    ).first()
    if court is None:
        return None
    _check_lead_time(data.starts_at)
    expire_stale_bookings(db, settings.booking_ttl_minutes)

    slots = _group_slots(db, court, data)
    group_public_id = uuid7()
    bookings = [
        Booking(
            slot_id=slot.id,
            group_public_id=group_public_id,
            customer_name=data.customer_name,
            customer_contact=data.customer_contact,
        )
        for slot in slots
    ]
    for slot in slots:
        slot.status = "booked"
    db.add_all(bookings)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    for booking in bookings:
        db.refresh(booking)
    return {
        "group_public_id": group_public_id,
        "hours": len(bookings),
        "total": sum(slot.price for slot in slots),
        "bookings": bookings,
    }


def list_group(db: Session, group_public_id: UUID) -> list[Booking]:
    stmt = (
        select(Booking)
        .where(Booking.group_public_id == group_public_id)
        .order_by(Booking.id)
    )
    return list(db.scalars(stmt).all())


def cancel_group(db: Session, group_public_id: UUID) -> list[Booking]:
    bookings = list_group(db, group_public_id)
    for booking in bookings:
        _release(db, booking)
    if bookings:
        db.commit()
        for booking in bookings:
            db.refresh(booking)
    return bookings


def confirm_booking(db: Session, booking: Booking) -> Booking | None:
    if booking.status == "cancelled":
        return None
    booking.status = "confirmed"
    db.commit()
    db.refresh(booking)
    return booking


def cancel_booking(db: Session, booking: Booking) -> Booking:
    _release(db, booking)
    db.commit()
    db.refresh(booking)
    return booking


def _release(db: Session, booking: Booking) -> None:
    """Mark cancelled and free the slot it held (caller commits)."""
    booking.status = "cancelled"
    slot = db.get(Slot, booking.slot_id)
    if slot is not None and slot.status == "booked":
        slot.status = "available"


def slot_public_id(db: Session, booking: Booking) -> UUID:
    return db.get(Slot, booking.slot_id).public_id


def detail(db: Session, booking: Booking) -> dict:
    """Slot, court, venue, total and payment state for one booking.

    List endpoints (manager dashboard, customer history) render straight from
    this instead of one request per row.
    """
    slot = db.get(Slot, booking.slot_id)
    court = db.get(Court, slot.court_id) if slot is not None else None
    venue = db.get(Venue, court.venue_id) if court is not None else None
    payment = db.scalars(
        select(Payment)
        .where(Payment.booking_id == booking.id)
        .order_by(Payment.id.desc())
    ).first()
    return {
        "slot": (
            None
            if slot is None
            else {
                "public_id": slot.public_id,
                "starts_at": slot.starts_at,
                "ends_at": slot.ends_at,
                "price": slot.price,
                "status": slot.status,
            }
        ),
        "court": (
            None
            if court is None
            else {
                "public_id": court.public_id,
                "name": court.name,
                "sport": court.sport,
            }
        ),
        "venue": (
            None
            if venue is None
            else {"public_id": venue.public_id, "name": venue.name}
        ),
        "total": slot.price if slot is not None else 0,
        "payment_status": payment.status if payment is not None else "unpaid",
    }
