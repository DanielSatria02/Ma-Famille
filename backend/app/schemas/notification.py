from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    public_id: UUID
    event: Literal["pending", "confirmed", "cancelled"]
    channel: Literal["email", "whatsapp"]
    recipient: str
    subject: str
    body: str
    # queued = waiting, sent = a provider accepted it, logged = only recorded
    # because no provider is configured, failed = the provider said no.
    status: Literal["queued", "sent", "logged", "failed"]
    transport: str
    error: str
    attempts: int
    sent_at: datetime | None = None
    created_at: datetime


class NotificationDispatchResult(BaseModel):
    """What one dispatch pass did with the queue."""

    transport: str
    sent: int = Field(ge=0)
    logged: int = Field(ge=0)
    failed: int = Field(ge=0)
    still_queued: int = Field(ge=0)
