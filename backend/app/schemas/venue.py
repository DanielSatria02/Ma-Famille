from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _clean_tags(tags: list[str]) -> list[str]:
    """Trim, drop blanks and de-duplicate while keeping the caller's order."""
    seen: list[str] = []
    for tag in tags:
        clean = tag.strip().lower()
        if clean and clean not in seen:
            seen.append(clean)
    return seen


class VenueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(default="", max_length=255)
    tags: list[str] = Field(default_factory=list, max_length=20)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        return _clean_tags(value)


class VenueUpdate(BaseModel):
    """Only the fields present are written; `"tags": []` clears them."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = Field(default=None, max_length=20)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _clean_tags(value)


class VenueResponse(BaseModel):
    public_id: UUID
    name: str
    address: str
    tags: list[str] = Field(default_factory=list)
    lat: float | None = None
    lng: float | None = None
    created_at: datetime
