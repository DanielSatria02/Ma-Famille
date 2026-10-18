"""Facility listings.

A "facility" is what a client books (the `courts` table). This module turns the
rows into the shape the pickers need: can it be booked right now, and if not,
why. Availability of the hours themselves comes from `/availability`.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.court import Court
from app.models.venue import Venue
from app.services import courts as court_service


def _venue(db: Session, venue_public_id: UUID) -> Venue | None:
    return db.scalars(
        select(Venue).where(Venue.public_id == venue_public_id)
    ).first()


def _entry(db: Session, court: Court, manager_view: bool) -> dict:
    venue = db.get(Venue, court.venue_id)
    priced = court_service.is_price_set(court)
    if court.is_active and priced:
        reason = None
    elif not court.is_active:
        reason = "inactive"
    else:
        reason = "no_rate"
    entry = {
        "public_id": court.public_id,
        "name": court.name,
        "kind": court.kind,
        "sport": court.sport,
        "venue": {"public_id": venue.public_id, "name": venue.name},
        "price_weekday": court.price_weekday,
        "price_weekend": court.price_weekend,
        "is_price_set": priced,
        "is_active": court.is_active,
        "is_bookable": reason is None,
        "unavailable_reason": reason,
    }
    if manager_view:
        entry["locked"] = not priced
    return entry


def list_facilities(
    db: Session,
    venue_public_id: UUID | None = None,
    kind: str | None = None,
    manager_view: bool = False,
) -> list[dict] | None:
    """Facilities for every venue, or one venue (None when that id is unknown)."""
    stmt = select(Court).join(Venue, Venue.id == Court.venue_id)
    if venue_public_id is not None:
        venue = _venue(db, venue_public_id)
        if venue is None:
            return None
        stmt = stmt.where(Court.venue_id == venue.id)
    if kind is not None:
        stmt = stmt.where(Court.kind == kind)
    stmt = stmt.order_by(Venue.id, Court.id)
    return [_entry(db, court, manager_view) for court in db.scalars(stmt).all()]
