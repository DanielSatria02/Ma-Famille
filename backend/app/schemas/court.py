from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.venue import _clean_image_url

Sport = Literal["futsal", "badminton"]
CourtKind = Literal["court", "office", "cafe"]


class CourtCreate(BaseModel):
    venue_public_id: UUID
    name: str = Field(min_length=1, max_length=120)
    sport: Sport
    kind: CourtKind = "court"
    # Omit or send null to keep the facility unpriced (not bookable).
    price_weekday: int | None = Field(default=None, ge=0)
    price_weekend: int | None = Field(default=None, ge=0)
    image_url: str | None = Field(default=None, max_length=300)

    @field_validator("image_url")
    @classmethod
    def _image(cls, value: str | None) -> str | None:
        return _clean_image_url(value)


class CourtUpdate(BaseModel):
    """Only the fields present in the payload are written, so sending
    `"price_weekday": null` clears the rate (explicit null, not "unchanged")."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: CourtKind | None = None
    price_weekday: int | None = Field(default=None, ge=0)
    price_weekend: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    image_url: str | None = Field(default=None, max_length=300)

    @field_validator("image_url")
    @classmethod
    def _image(cls, value: str | None) -> str | None:
        return _clean_image_url(value)


class CourtResponse(BaseModel):
    public_id: UUID
    venue_public_id: UUID
    name: str
    sport: Sport
    kind: CourtKind
    price_weekday: int | None = None
    price_weekend: int | None = None
    is_price_set: bool
    is_active: bool
    image_url: str | None = None
    created_at: datetime
