from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.venue import Venue
from app.schemas.venue import VenueCreate, VenueUpdate


def list_venues(
    db: Session, q: str | None = None, tag: str | None = None
) -> list[Venue]:
    """All venues, optionally narrowed by free-text search or one tag.

    Filtering happens in Python: the table is small and tags live in a JSON
    column whose operators differ between Postgres and SQLite (tests).
    """
    venues = list(db.scalars(select(Venue).order_by(Venue.id)).all())
    if q:
        needle = q.strip().lower()
        venues = [
            venue
            for venue in venues
            if needle in venue.name.lower() or needle in venue.address.lower()
        ]
    if tag:
        wanted = tag.strip().lower()
        venues = [venue for venue in venues if wanted in (venue.tags or [])]
    return venues


def all_tags(db: Session) -> list[str]:
    """Tag vocabulary across venues, so clients need not hardcode filters."""
    tags: set[str] = set()
    for venue in db.scalars(select(Venue)).all():
        tags.update(venue.tags or [])
    return sorted(tags)


def get_by_public_id(db: Session, public_id: UUID) -> Venue | None:
    return db.scalars(select(Venue).where(Venue.public_id == public_id)).first()


def create_venue(db: Session, data: VenueCreate) -> Venue:
    venue = Venue(
        name=data.name,
        address=data.address,
        tags=data.tags,
        lat=data.lat,
        lng=data.lng,
    )
    db.add(venue)
    db.commit()
    db.refresh(venue)
    return venue


def update_venue(db: Session, venue: Venue, data: VenueUpdate) -> Venue:
    provided = data.model_fields_set
    if data.name is not None and "name" in provided:
        venue.name = data.name
    if data.address is not None and "address" in provided:
        venue.address = data.address
    if "tags" in provided and data.tags is not None:
        venue.tags = data.tags
    if "lat" in provided:
        venue.lat = data.lat
    if "lng" in provided:
        venue.lng = data.lng
    db.commit()
    db.refresh(venue)
    return venue


def delete_venue(db: Session, venue: Venue) -> None:
    db.delete(venue)
    db.commit()
