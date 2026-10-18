from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class VenueClosureCreate(BaseModel):
    """A date range the venue is shut (holiday, renovation, private event)."""

    starts_on: date
    ends_on: date
    reason: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def _check(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on before starts_on")
        if (self.ends_on - self.starts_on).days > 90:
            raise ValueError("closure too long (max 90 days)")
        return self


class VenueClosureResponse(BaseModel):
    public_id: UUID
    venue_public_id: UUID
    starts_on: date
    ends_on: date
    days: int
    reason: str


class VenueClosureCreated(VenueClosureResponse):
    # Bookings already in that window: the manager has to contact those people.
    affected_bookings: int = 0
