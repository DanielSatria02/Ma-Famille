from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.court import Court
from app.models.venue import Venue
from app.schemas.court import CourtCreate, CourtUpdate


def _venue_id(db: Session, venue_public_id: UUID) -> int | None:
    venue = db.scalars(select(Venue).where(Venue.public_id == venue_public_id)).first()
    return venue.id if venue else None


def is_price_set(court: Court) -> bool:
    """Both rates present. An unpriced facility is listed but not bookable."""
    return court.price_weekday is not None and court.price_weekend is not None


def rate_for(court: Court, day: date) -> int | None:
    """Rate for a calendar day: weekend (Sat/Sun) is priced separately."""
    return court.price_weekend if day.weekday() >= 5 else court.price_weekday


def peak_active(court: Court) -> bool:
    """Is the peak overlay switchable on?

    Only when all three peak fields are present. A half-set window (say a rate
    with no hours) is treated as "no peak" rather than an error: the day rate
    still books the court, and the manager sees the window they left incomplete.
    """
    return (
        court.price_peak is not None
        and court.peak_start_hour is not None
        and court.peak_end_hour is not None
    )


def rate_for_hour(court: Court, day: date, hour: int) -> int | None:
    """Rate for one hour: the peak rate wins inside the peak window.

    The window is half-open — [start, end) — so a 17–21 evening peak prices the
    17, 18, 19 and 20 hours, and the 21 hour falls back to the day rate. Outside
    the window (or with no peak set) this is just `rate_for`.
    """
    if peak_active(court):
        # Guard the comparison so a bad window (start > end) never matches
        # every hour by accident.
        start, end = court.peak_start_hour, court.peak_end_hour
        if start <= end and start <= hour < end:
            return court.price_peak
    return rate_for(court, day)


def list_courts(db: Session, venue_public_id: UUID | None = None) -> list[Court]:
    stmt = select(Court).order_by(Court.id)
    if venue_public_id is not None:
        venue_id = _venue_id(db, venue_public_id)
        if venue_id is None:
            return []
        stmt = stmt.where(Court.venue_id == venue_id)
    return list(db.scalars(stmt).all())


def get_by_public_id(db: Session, public_id: UUID) -> Court | None:
    return db.scalars(select(Court).where(Court.public_id == public_id)).first()


def create_court(db: Session, data: CourtCreate) -> Court | None:
    venue_id = _venue_id(db, data.venue_public_id)
    if venue_id is None:
        return None
    court = Court(
        venue_id=venue_id,
        name=data.name,
        sport=data.sport,
        kind=data.kind,
        price_weekday=data.price_weekday,
        price_weekend=data.price_weekend,
        price_peak=data.price_peak,
        peak_start_hour=data.peak_start_hour,
        peak_end_hour=data.peak_end_hour,
    )
    db.add(court)
    db.commit()
    db.refresh(court)
    return court


def update_court(db: Session, court: Court, data: CourtUpdate) -> Court:
    """Write only the fields the client sent, so an explicit null clears a rate."""
    provided = data.model_fields_set
    if data.name is not None and "name" in provided:
        court.name = data.name
    if data.kind is not None and "kind" in provided:
        court.kind = data.kind
    if "price_weekday" in provided:
        court.price_weekday = data.price_weekday
    if "price_weekend" in provided:
        court.price_weekend = data.price_weekend
    if "price_peak" in provided:
        court.price_peak = data.price_peak
    if "peak_start_hour" in provided:
        court.peak_start_hour = data.peak_start_hour
    if "peak_end_hour" in provided:
        court.peak_end_hour = data.peak_end_hour
    if data.is_active is not None and "is_active" in provided:
        court.is_active = data.is_active
    if "image_url" in provided:
        court.image_url = data.image_url
    db.commit()
    db.refresh(court)
    return court


def deactivate_court(db: Session, court: Court) -> None:
    court.is_active = False
    db.commit()


def venue_public_id(db: Session, court: Court) -> UUID:
    venue = db.get(Venue, court.venue_id)
    return venue.public_id
