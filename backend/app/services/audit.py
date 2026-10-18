"""Audit trail: record every manager and system change, read it back for the dashboard.

`record()` is append-only and never raises — if the DB is briefly unavailable, a
business write must still succeed, so an audit failure is logged and swallowed
rather than rolled back. The trail is a nice-to-have; the booking is not.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent

logger = logging.getLogger(__name__)

# Keep the trail readable: cap the free-text note so a runaway value cannot
# bloat a row.
MAX_DETAIL = 500


def record(
    db: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_public_id: str | None = None,
    detail: str | None = None,
) -> AuditEvent | None:
    """Append one audit row and commit it. Returns None if it could not be saved.

    Committed on its own transaction so a later rollback of the caller's work
    (a failed booking, say) does not erase the fact that someone tried.
    """
    event = AuditEvent(
        actor=actor or "system",
        action=action,
        entity_type=entity_type,
        entity_public_id=str(entity_public_id) if entity_public_id else None,
        detail=(detail or "")[:MAX_DETAIL] or None,
    )
    try:
        db.add(event)
        db.commit()
        db.refresh(event)
        return event
    except Exception:  # noqa: BLE001 — the trail must never break the write it logs
        logger.exception("audit record failed (%s %s)", action, entity_type)
        db.rollback()
        return None


def list_events(
    db: Session,
    *,
    entity_type: str | None = None,
    entity_public_id: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditEvent]:
    """Newest-first slice of the trail, optionally narrowed to one thing."""
    stmt = select(AuditEvent)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_public_id:
        stmt = stmt.where(AuditEvent.entity_public_id == str(entity_public_id))
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if actor:
        stmt = stmt.where(AuditEvent.actor == actor)
    stmt = stmt.order_by(AuditEvent.id.desc())
    if offset:
        stmt = stmt.offset(offset)
    return list(db.scalars(stmt.limit(limit)).all())


def count_events(
    db: Session,
    *,
    entity_type: str | None = None,
    entity_public_id: str | None = None,
    action: str | None = None,
    actor: str | None = None,
) -> int:
    """How many rows `list_events` would return without the page slice."""
    from sqlalchemy import func

    stmt = select(func.count()).select_from(AuditEvent)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_public_id:
        stmt = stmt.where(AuditEvent.entity_public_id == str(entity_public_id))
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if actor:
        stmt = stmt.where(AuditEvent.actor == actor)
    return int(db.scalar(stmt) or 0)


def format_when(event: AuditEvent) -> str:
    """Human-readable timestamp for a trail row (UTC)."""
    when: datetime | None = event.created_at
    return when.strftime("%Y-%m-%d %H:%M:%S") if when else ""
