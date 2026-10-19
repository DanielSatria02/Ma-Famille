from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

PaymentKind = Literal["deposit", "full"]
PaymentStatus = Literal["unpaid", "paid", "failed", "refunded"]


class PaymentCreate(BaseModel):
    booking_public_id: UUID
    amount: int = Field(ge=0)
    kind: PaymentKind = "deposit"


class PaymentResponse(BaseModel):
    public_id: UUID
    booking_public_id: UUID
    amount: int
    kind: PaymentKind
    status: PaymentStatus
    invoice_number: str | None = None
    provider_status: str | None = None
    failure_reason: str | None = None
    refunded_at: datetime | None = None
    # The hosted checkout page, so a customer who closed it can go back to it
    # without a second invoice being opened.
    checkout_url: str | None = None
    created_at: datetime


class PaymentInitiateResponse(BaseModel):
    invoice_number: str
    checkout_url: str
    token_id: str = ""


class PaymentRefundResponse(BaseModel):
    payment: PaymentResponse
    # "doku" = the provider was asked and answered; "local" = bookkeeping only,
    # because there are no keys to ask with (the money move stays manual).
    provider: Literal["doku", "local"]
    detail: str
    provider_status: str = ""


class DokuWebhookAck(BaseModel):
    invoice_number: str
    payment_status: str
    detail: str = "matched"
