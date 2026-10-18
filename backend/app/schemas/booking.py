from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.payment import PaymentStatus

BookingStatus = Literal["pending", "confirmed", "cancelled"]


class BookingSlotInfo(BaseModel):
    public_id: UUID
    starts_at: datetime
    ends_at: datetime
    price: int
    status: str


class BookingCourtInfo(BaseModel):
    public_id: UUID
    name: str
    sport: str


class BookingVenueInfo(BaseModel):
    public_id: UUID
    name: str


class BookingCreate(BaseModel):
    slot_public_id: UUID
    customer_name: str = Field(min_length=1, max_length=120)
    customer_contact: str = Field(min_length=3, max_length=60)


class BookingRangeCreate(BaseModel):
    """Book a whole-hour range on one court in a single call.

    `starts_at`/`ends_at` are wall times of the court (`2026-10-20T09:00:00`),
    whole hours, inside the same day. The range becomes one group of bookings.
    """

    court_public_id: UUID
    starts_at: datetime
    ends_at: datetime
    customer_name: str = Field(min_length=1, max_length=120)
    customer_contact: str = Field(min_length=3, max_length=60)

    @model_validator(mode="after")
    def _check_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.starts_at.date() != self.ends_at.date():
            raise ValueError("a booking cannot span two days")
        for label, moment in (("starts_at", self.starts_at), ("ends_at", self.ends_at)):
            if moment.minute or moment.second or moment.microsecond:
                raise ValueError(f"{label} must be a whole hour")
        return self


class BookingResponse(BaseModel):
    public_id: UUID
    slot_public_id: UUID
    group_public_id: UUID | None = None
    customer_name: str
    customer_contact: str
    status: BookingStatus
    created_at: datetime
    # Joined detail so list views (manager dashboard, booking history) render
    # without a second round trip per row.
    slot: BookingSlotInfo | None = None
    court: BookingCourtInfo | None = None
    venue: BookingVenueInfo | None = None
    total: int = 0
    payment_status: PaymentStatus = "unpaid"


class BookingRangeResponse(BaseModel):
    group_public_id: UUID
    hours: int = Field(ge=1)
    total: int = Field(ge=0)
    bookings: list[BookingResponse]
