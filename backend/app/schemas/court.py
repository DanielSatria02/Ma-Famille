from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.venue import _clean_image_url

Sport = Literal["futsal", "badminton"]
CourtKind = Literal["court", "office", "cafe"]


def _check_peak_window(price_peak, start_hour, end_hour):
    """A peak window is only real when it is complete and points forwards.

    Any peak field set at all means the manager meant to configure peak time, so
    a partial window is an error rather than silently ignored — otherwise a typo
    would leave a rate that never applies and no hint why.
    """
    values = (price_peak, start_hour, end_hour)
    if all(v is None for v in values):
        return values
    if any(v is None for v in values):
        raise ValueError(
            "peak pricing needs price_peak, peak_start_hour and peak_end_hour together"
        )
    if not 0 <= start_hour <= 23 or not 1 <= end_hour <= 24:
        raise ValueError("peak hours must be within 0..23 (start) and 1..24 (end)")
    if start_hour >= end_hour:
        raise ValueError("peak_start_hour must be earlier than peak_end_hour")
    return values


class CourtCreate(BaseModel):
    venue_public_id: UUID
    name: str = Field(min_length=1, max_length=120)
    sport: Sport
    kind: CourtKind = "court"
    # Omit or send null to keep the facility unpriced (not bookable).
    price_weekday: int | None = Field(default=None, ge=0)
    price_weekend: int | None = Field(default=None, ge=0)
    # Optional premium rate for [peak_start_hour, peak_end_hour). All three or none.
    price_peak: int | None = Field(default=None, ge=0)
    peak_start_hour: int | None = Field(default=None, ge=0, le=23)
    peak_end_hour: int | None = Field(default=None, ge=1, le=24)
    image_url: str | None = Field(default=None, max_length=300)

    @field_validator("image_url")
    @classmethod
    def _image(cls, value: str | None) -> str | None:
        return _clean_image_url(value)

    @model_validator(mode="after")
    def _peak(self):
        _check_peak_window(self.price_peak, self.peak_start_hour, self.peak_end_hour)
        return self


class CourtUpdate(BaseModel):
    """Only the fields present in the payload are written, so sending
    `\"price_weekday\": null` clears the rate (explicit null, not \"unchanged\")."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: CourtKind | None = None
    price_weekday: int | None = Field(default=None, ge=0)
    price_weekend: int | None = Field(default=None, ge=0)
    price_peak: int | None = Field(default=None, ge=0)
    peak_start_hour: int | None = Field(default=None, ge=0, le=23)
    peak_end_hour: int | None = Field(default=None, ge=1, le=24)
    is_active: bool | None = None
    image_url: str | None = Field(default=None, max_length=300)

    @field_validator("image_url")
    @classmethod
    def _image(cls, value: str | None) -> str | None:
        return _clean_image_url(value)

    @model_validator(mode="after")
    def _peak(self):
        # Validate only the peak fields the client actually sent, so a payload
        # that merely clears `price_weekday` does not trip the peak rules.
        sent = {
            f: getattr(self, f)
            for f in ("price_peak", "peak_start_hour", "peak_end_hour")
            if f in self.model_fields_set
        }
        if sent:
            _check_peak_window(
                sent.get("price_peak"),
                sent.get("peak_start_hour"),
                sent.get("peak_end_hour"),
            )
        return self


class CourtResponse(BaseModel):
    public_id: UUID
    venue_public_id: UUID
    name: str
    sport: Sport
    kind: CourtKind
    price_weekday: int | None = None
    price_weekend: int | None = None
    price_peak: int | None = None
    peak_start_hour: int | None = None
    peak_end_hour: int | None = None
    is_price_set: bool
    is_active: bool
    image_url: str | None = None
    created_at: datetime
