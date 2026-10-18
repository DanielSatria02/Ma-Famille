from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

PromotionKind = Literal["percent", "amount"]


class PromotionCreate(BaseModel):
    """A new code. `venue_public_id` nil means it works at every venue."""

    code: str = Field(min_length=3, max_length=40)
    kind: PromotionKind = "percent"
    # percent: 1–100. amount: rupiah off.
    value: int = Field(ge=1)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    max_uses: int | None = Field(default=None, ge=1)
    is_active: bool = True
    venue_public_id: UUID | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        # Stored upper-case so `hemat` and `HEMAT` are one voucher.
        return value.strip().upper()

    @model_validator(mode="after")
    def _bounds(self):
        if self.kind == "percent" and self.value > 100:
            raise ValueError("a percent code cannot be over 100")
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        return self


class PromotionUpdate(BaseModel):
    """Only the fields present are written; an explicit null clears a bound."""

    kind: PromotionKind | None = None
    value: int | None = Field(default=None, ge=1)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    max_uses: int | None = Field(default=None, ge=1)
    is_active: bool | None = None

    @model_validator(mode="after")
    def _bounds(self):
        if self.kind == "percent" and self.value is not None and self.value > 100:
            raise ValueError("a percent code cannot be over 100")
        return self


class PromotionResponse(BaseModel):
    public_id: UUID
    code: str
    kind: PromotionKind
    value: int
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    max_uses: int | None = None
    used_count: int
    is_active: bool
    venue_public_id: UUID | None = None
    created_at: datetime


class PromotionCheck(BaseModel):
    """What a customer sees after typing a code at checkout.

    `ok` false means the code was refused; `reason` says why in words they can
    act on. `discount` and `amount_due` are only meaningful when `ok` is true.
    """

    ok: bool
    code: str | None = None
    reason: str | None = None
    discount: int = 0
    gross: int = 0
    amount_due: int = 0
