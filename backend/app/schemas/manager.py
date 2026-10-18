from datetime import date

from pydantic import BaseModel, Field


class OccupancyPoint(BaseModel):
    day: date
    total_slots: int = Field(ge=0)
    booked_slots: int = Field(ge=0)
    occupancy_rate: float = Field(ge=0, le=1)


class ManagerStats(BaseModel):
    """Dashboard counters. One "visit" is one booking group, not one hour."""

    day: date
    week_start: date
    week_end: date
    todays_bookings: int = Field(ge=0)
    weekly_visitors: int = Field(ge=0)
    cancelled_bookings: int = Field(ge=0)
