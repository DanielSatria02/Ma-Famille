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
    if data.is_active is not None and "is_active" in provided:
        court.is_active = data.is_active
    db.commit()
    db.refresh(court)
    return court


def deactivate_court(db: Session, court: Court) -> None:
    court.is_active = False
    db.commit()


def venue_public_id(db: Session, court: Court) -> UUID:
    venue = db.get(Venue, court.venue_id)
    return venue.public_id
