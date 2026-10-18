from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin


class AuditEvent(Base, PKMixin, PublicIdMixin):
    """One row per "something changed" — append-only, never updated or deleted.

    `actor` is who did it (a manager token label, a customer contact, or a
    system process like an expiry sweep). `action` is a short verb
    (`venue.update`, `booking.confirm`, `payment.refund`). `entity_type` +
    `entity_public_id` point at what changed. `detail` is a free-text note so a
    human reading the trail can see the old→new without guessing.

    Kept as a plain text `detail` rather than a JSON blob: the trail is read by
    people, not replayed by code, and a string cannot drift out of sync with the
    columns it describes.
    """

    __tablename__ = "audit_events"

    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # String, not FK: the pointed-at row may be deleted later and the trail must
    # outlive it.
    entity_public_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
