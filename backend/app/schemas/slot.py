from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

SlotStatus = Literal["available", "held", "booked", "blocked"]


class SlotCreate(BaseModel):
    court_public_id: UUID
    starts_at: datetime
    ends_at: datetime
    price: int = Field(ge=0)

    @model_validator(mode="after")
    def _ends_after_starts(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class SlotUpdate(BaseModel):
    status: SlotStatus | None = None
    price: int | None = Field(default=None, ge=0)


class SlotResponse(BaseModel):
    public_id: UUID
    court_public_id: UUID
    starts_at: datetime
    ends_at: datetime
    price: int
    status: SlotStatus


class AvailabilityQuery(BaseModel):
    court_public_id: UUID
    day: date


class SlotGenerateRequest(BaseModel):
    """Materialise hourly slots from a venue's opening hours.

    Exactly one target: `court_public_id` (single court) or `venue_public_id`
    (every active court of that venue). Re-running is safe — slots that already
    exist for a start time are skipped instead of duplicated.
    """

    from_day: date
    to_day: date
    court_public_id: UUID | None = None
    venue_public_id: UUID | None = None

    @model_validator(mode="after")
    def _check(self):
        if (self.court_public_id is None) == (self.venue_public_id is None):
            raise ValueError(
                "provide exactly one of court_public_id or venue_public_id"
            )
        if self.to_day < self.from_day:
            raise ValueError("to_day before from_day")
        if (self.to_day - self.from_day).days > 60:
            raise ValueError("range too wide (max 60 days)")
        return self


class SlotBlockRequest(BaseModel):
    """Close (or reopen) a window of hours, for one court or a whole venue.

    The manager workflow: "facility X is closed 09:00-12:00 next Saturday".
    Hours that are already booked are never touched.
    """

    from_day: date
    to_day: date
    from_hour: int = Field(ge=0, le=23)
    to_hour: int = Field(ge=1, le=24)
    status: Literal["blocked", "available"] = "blocked"
    court_public_id: UUID | None = None
    venue_public_id: UUID | None = None

    @model_validator(mode="after")
    def _check(self):
        if (self.court_public_id is None) == (self.venue_public_id is None):
            raise ValueError(
                "provide exactly one of court_public_id or venue_public_id"
            )
        if self.to_day < self.from_day:
            raise ValueError("to_day before from_day")
        if (self.to_day - self.from_day).days > 60:
            raise ValueError("range too wide (max 60 days)")
        if self.to_hour <= self.from_hour:
            raise ValueError("to_hour must be after from_hour")
        return self


class SlotBlockResponse(BaseModel):
    from_day: date
    to_day: date
    from_hour: int
    to_hour: int
    status: SlotStatus
    courts: int
    days: int
    updated: int
    unchanged: int
    # Hours left alone because somebody is playing then.
    skipped_booked: int
    # Hours with no slot row: nothing to open or close.
    skipped_missing: int


class SlotGenerateResponse(BaseModel):
    from_day: date
    to_day: date
    courts: int
    created: int
    skipped_existing: int
    skipped_closed_days: int
    # Court-days left alone because of a closure (holiday) on the venue.
    skipped_closure_days: int = 0
    # Court-days left alone because the manager has not priced them.
    skipped_unpriced: int = 0
