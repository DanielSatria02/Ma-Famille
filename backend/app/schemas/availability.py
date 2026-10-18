from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

HourStatus = Literal["available", "booked", "held", "blocked", "unavailable"]


class DayAvailability(BaseModel):
    """Per-day roll-up used by the availability calendar."""

    day: date
    total_hours: int = Field(ge=0)
    booked_hours: int = Field(ge=0)
    free_hours: int = Field(ge=0)


class HourAvailability(BaseModel):
    """One opening hour of a court on a day.

    `unavailable` means no slot row exists for that hour (not generated yet or
    booked out of the opening window), so clients can render the full day
    instead of guessing why an hour is missing.
    """

    hour: int = Field(ge=0, le=23)
    starts_at: datetime | None = None
    status: HourStatus
    price: int | None = None
    slot_public_id: UUID | None = None


class DayHoursResponse(BaseModel):
    court_public_id: UUID
    day: date
    day_of_week: int = Field(ge=0, le=6)
    is_closed: bool
    opens_at: str | None = None
    closes_at: str | None = None
    hours: list[HourAvailability]
