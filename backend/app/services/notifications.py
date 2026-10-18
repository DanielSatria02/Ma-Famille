"""Guest notifications: an outbox written by booking events.

`queue_event` never talks to a provider — it writes a row, so a booking flow can
never fail because a mail server was slow. `dispatch_pending` is the only place
that leaves the building, and it says honestly what happened:

- `sent`   the provider accepted it
- `logged` no provider for that channel is configured, so the message was only
  recorded (server log + row) — dev and demo mode
- `failed` the provider rejected it (the error is kept on the row)
- still `queued` the transport is configured but not for this channel
"""

import logging
import re
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.booking import Booking
from app.models.court import Court
from app.models.notification import Notification
from app.models.slot import Slot
from app.models.venue import Venue

logger = logging.getLogger("ma-famille.notifications")

EVENTS = ("pending", "confirmed", "cancelled")
TITLES = {
    "pending": "Booking received",
    "confirmed": "Booking confirmed",
    "cancelled": "Booking cancelled",
}
WHATSAPP_URL = "https://graph.facebook.com/v21.0/{phone_id}/messages"


class NotifyNotConfigured(RuntimeError):
    """The configured transport cannot carry this channel."""


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def channel_for(contact: str) -> str:
    """Email address → email, anything else (a phone) → whatsapp."""
    return "email" if "@" in contact else "whatsapp"


def whatsapp_number(contact: str) -> str:
    """WhatsApp wants digits with the country code: 0812… and +62 812… → 62812…"""
    digits = re.sub(r"\D", "", contact)
    if digits.startswith("0"):
        return f"62{digits[1:]}"
    if digits.startswith("8"):
        return f"62{digits}"
    return digits


def _describe(db: Session, bookings: list[Booking]) -> tuple[str, str]:
    """Subject tail and body for a visit (its first and last booked hour)."""
    first, last = bookings[0], bookings[-1]
    start_slot = db.get(Slot, first.slot_id)
    end_slot = db.get(Slot, last.slot_id)
    court = db.get(Court, start_slot.court_id)
    venue = db.get(Venue, court.venue_id)
    starts_at = _naive(start_slot.starts_at)
    ends_at = _naive(end_slot.ends_at)
    hours = len(bookings)
    total = sum(
        db.get(Slot, booking.slot_id).price for booking in bookings
    )
    when = (
        f"{starts_at:%a %d %b %Y} {starts_at:%H:%M}-{ends_at:%H:%M}"
        f" ({hours} hour{'s' if hours != 1 else ''})"
    )
    subject = f"{court.name} at {venue.name}, {when}"
    body = (
        f"Hi {first.customer_name},\n\n"
        f"{TITLES.get(first.status, 'Booking update')}: {court.name} at {venue.name}\n"
        f"{when}\nTotal: {total}\n\n"
        f"Take care of your booking with this contact number: {first.customer_contact}.\n"
        f"— {venue.name}"
    )
    return subject, body


def queue_event(db: Session, bookings: list[Booking], event: str) -> Notification | None:
    """Write the outbox row for a visit. Returns None when there is nobody to tell."""
    if not bookings or event not in EVENTS:
        return None
    contact = (bookings[0].customer_contact or "").strip()
    if not contact:
        return None
    subject, body = _describe(db, bookings)
    row = Notification(
        booking_id=bookings[0].id,
        group_public_id=bookings[0].group_public_id,
        event=event,
        channel=channel_for(contact),
        recipient=contact,
        subject=f"{TITLES[event]}: {subject}",
        body=body,
        status="queued",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_notifications(
    db: Session, status: str | None = None, limit: int = 50
) -> list[Notification]:
    stmt = select(Notification)
    if status:
        stmt = stmt.where(Notification.status == status)
    stmt = stmt.order_by(Notification.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def counts_by_status(db: Session) -> dict[str, int]:
    counts = {status: 0 for status in ("queued", "sent", "logged", "failed")}
    for row in db.scalars(select(Notification)).all():
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


def _send_email(row: Notification) -> None:
    message = EmailMessage()
    message["From"] = settings.notify_from
    message["To"] = row.recipient
    message["Subject"] = row.subject
    message.set_content(row.body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


def _send_whatsapp(row: Notification) -> None:
    response = httpx.post(
        WHATSAPP_URL.format(phone_id=settings.whatsapp_phone_id),
        json={
            "messaging_product": "whatsapp",
            "to": whatsapp_number(row.recipient),
            "type": "text",
            "text": {"body": f"{row.subject}\n\n{row.body}"},
        },
        headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
        timeout=10,
    )
    response.raise_for_status()


def _deliver(row: Notification) -> str:
    """Transport used for one message. `log` means recorded, not delivered."""
    transport = settings.notify_transport
    if transport == "smtp":
        if row.channel != "email":
            raise NotifyNotConfigured(
                f"smtp cannot carry a {row.channel} message (edit notify_transport)"
            )
        if not settings.smtp_configured:
            raise NotifyNotConfigured("SMTP_HOST is not set")
        _send_email(row)
        return "smtp"
    if transport == "whatsapp":
        if row.channel != "whatsapp":
            raise NotifyNotConfigured(
                f"whatsapp cannot carry a {row.channel} message (edit notify_transport)"
            )
        if not settings.whatsapp_configured:
            raise NotifyNotConfigured(
                "WHATSAPP_TOKEN / WHATSAPP_PHONE_ID are not set"
            )
        _send_whatsapp(row)
        return "whatsapp"
    logger.info(
        "notification[%s] to %s via %s: %s", row.event, row.recipient, row.channel, row.subject
    )
    return "log"


def dispatch_pending(db: Session, limit: int = 20) -> dict:
    """Work the queue once. Returns the tally, never raises for a bad provider."""
    rows = db.scalars(
        select(Notification)
        .where(Notification.status == "queued")
        .order_by(Notification.id)
        .limit(limit)
    ).all()

    sent = logged = failed = still_queued = 0
    for row in rows:
        row.attempts += 1
        try:
            transport = _deliver(row)
        except NotifyNotConfigured as exc:
            row.error = str(exc)[:240]
            still_queued += 1
        except Exception as exc:  # provider said no: keep the reason on the row
            row.status = "failed"
            row.error = str(exc)[:240]
            failed += 1
        else:
            row.transport = transport
            row.error = ""
            row.sent_at = datetime.now(UTC)
            if transport == "log":
                row.status = "logged"
                logged += 1
            else:
                row.status = "sent"
                sent += 1

    if rows:
        db.commit()
    return {
        "transport": settings.notify_transport,
        "sent": sent,
        "logged": logged,
        "failed": failed,
        "still_queued": still_queued,
    }
