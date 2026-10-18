"""Domain models.

Every model module must be imported here so Alembic autogenerate sees it.
"""

from app.db.base import Base
from app.models.booking import Booking
from app.models.court import Court
from app.models.payment import Payment
from app.models.slot import Slot
from app.models.venue import Venue
from app.models.venue_closure import VenueClosure
from app.models.venue_hours import VenueHours

__all__ = [
    "Base",
    "Booking",
    "Court",
    "Payment",
    "Slot",
    "Venue",
    "VenueClosure",
    "VenueHours",
]
