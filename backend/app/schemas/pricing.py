from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class HourQuote(BaseModel):
    hour: int = Field(ge=0, le=23)
    starts_at: datetime
    price: int = Field(ge=0)
    slot_public_id: UUID | None = None
    status: str | None = None


class PricingQuote(BaseModel):
    """Price of a whole-hour range before anyone commits to it.

    `hourly_rate` is the first hour's rate; weekend hours may differ, so the
    per-hour `breakdown` is the authoritative list.
    """

    court_public_id: UUID
    court_name: str
    starts_at: datetime
    ends_at: datetime
    hours: int = Field(ge=1)
    hourly_rate: int = Field(ge=0)
    total: int = Field(ge=0)
    is_bookable: bool
    breakdown: list[HourQuote]
