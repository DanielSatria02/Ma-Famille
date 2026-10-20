from uuid import UUID

from sqlalchemy import delete, func, select
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
    if "image_url" in provided:
        venue.image_url = data.image_url
    db.commit()
    db.refresh(venue)
    return venue


class VenueNotEmptyError(Exception):
    """The club still holds a customer's data, so it cannot be deleted.

    A booking belongs to the person who made it and a review belongs to the
    person who wrote it. Neither is the manager's to erase, and the foreign
    keys do not cascade for exactly that reason — so the delete is refused
    and the error says what is in the way.

    Everything the manager owns — the courts, their slots, the opening hours,
    the closure dates, the discount codes — goes with the club.
    """

    def __init__(self, blockers: dict[str, int]):
        super().__init__("the club still holds a customer's data")
        self.blockers = blockers
        self.status_code = 409

    @property
    def message(self) -> str:
        parts = [f"{count} {name}" for name, count in self.blockers.items() if count]
        return (
            "this club still has "
            + ", ".join(parts)
            + " — those belong to customers and cannot be deleted here"
        )


def _customer_rows(db: Session, venue: Venue) -> dict[str, int]:
    """What points at this club that belongs to a customer."""
    from app.models.booking import Booking
    from app.models.court import Court
    from app.models.review import Review
    from app.models.slot import Slot

    court_ids = select(Court.id).where(Court.venue_id == venue.id)
    slot_ids = select(Slot.id).where(Slot.court_id.in_(court_ids))
    counts = {
        "bookings": db.scalar(
            select(func.count(Booking.id)).where(Booking.slot_id.in_(slot_ids))
        ),
        "reviews": db.scalar(
            select(func.count(Review.id)).where(Review.venue_id == venue.id)
        ),
    }
    return {name: count for name, count in counts.items() if count}


def _delete_manager_rows(db: Session, venue: Venue) -> None:
    """Remove everything under this club that the manager owns."""
    from app.models.court import Court
    from app.models.promotion import Promotion
    from app.models.slot import Slot
    from app.models.venue_closure import VenueClosure
    from app.models.venue_hours import VenueHours

    court_ids = select(Court.id).where(Court.venue_id == venue.id)
    # Slots first: the courts point at nothing, the slots point at the courts.
    db.execute(delete(Slot).where(Slot.court_id.in_(court_ids)))
    db.execute(delete(VenueHours).where(VenueHours.venue_id == venue.id))
    db.execute(delete(VenueClosure).where(VenueClosure.venue_id == venue.id))
    db.execute(delete(Promotion).where(Promotion.venue_id == venue.id))
    db.execute(delete(Court).where(Court.venue_id == venue.id))


def delete_venue(db: Session, venue: Venue) -> None:
    blockers = _customer_rows(db, venue)
    if blockers:
        raise VenueNotEmptyError(blockers)
    _delete_manager_rows(db, venue)
    db.delete(venue)
    db.commit()
