from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    """One row of the trail: who changed what, and when."""

    public_id: UUID
    actor: str
    action: str
    entity_type: str
    entity_public_id: str | None = None
    detail: str | None = None
    created_at: datetime
