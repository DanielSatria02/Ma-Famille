from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ReviewCreate(BaseModel):
    """A rating left after a visit.

    `venue_public_id` is the venue being rated; the visit behind it is found
    from the caller, never sent, so a rating cannot be aimed at someone else's
    booking.
    """

    venue_public_id: UUID
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        # An empty box should read as "no comment", not as a one-space one.
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ReviewResponse(BaseModel):
    public_id: UUID
    venue_public_id: UUID
    # The writer as the venue shows them: their display name when they have an
    # account, otherwise just the contact they booked with.
    author: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = None
    created_at: datetime
    # Set when the caller wrote this one, so the UI can offer editing.
    mine: bool = False


class VenueRatingResponse(BaseModel):
    """What a venue page leads with."""

    venue_public_id: UUID
    average: float
    count: int
    distribution: dict[str, int] = Field(default_factory=dict)
