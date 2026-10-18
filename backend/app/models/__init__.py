"""Domain models.

Every model module must be imported here so Alembic autogenerate sees it.
"""

from app.db.base import Base
from app.models.audit import AuditEvent
from app.models.booking import Booking
from app.models.court import Court
from app.models.customer import Customer
from app.models.customer_session import CustomerSession
from app.models.notification import Notification
from app.models.payment import Payment
from app.models.promotion import Promotion
from app.models.revoked_token import RevokedToken
from app.models.slot import Slot
from app.models.venue import Venue
from app.models.venue_closure import VenueClosure
from app.models.venue_hours import VenueHours

__all__ = [
    "AuditEvent",
    "Base",
    "Booking",
    "Court",
    "Customer",
    "CustomerSession",
    "Notification",
    "Payment",
    "Promotion",
    "RevokedToken",
    "Slot",
    "Venue",
    "VenueClosure",
    "VenueHours",
]
