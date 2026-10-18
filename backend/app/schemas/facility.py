from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.court import CourtKind, Sport

UnavailableReason = Literal["inactive", "no_rate"]


class FacilityVenueInfo(BaseModel):
    public_id: UUID
    name: str


class FacilityResponse(BaseModel):
    """A bookable facility as the client picker needs it."""

    public_id: UUID
    name: str
    kind: CourtKind
    sport: Sport
    venue: FacilityVenueInfo
    price_weekday: int | None = None
    price_weekend: int | None = None
    is_price_set: bool
    is_active: bool
    is_bookable: bool
    unavailable_reason: UnavailableReason | None = None
    image_url: str | None = None


class ManagerFacilityResponse(FacilityResponse):
    """Manager view: `locked` marks a facility that cannot be switched on
    until a rate is set (the switch in the venue-status panel)."""

    locked: bool
