from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.payment import Payment
from app.schemas.payment import PaymentKind

# Statuses a payment can hold, and what moves it on.
LIVE_STATUSES = ("unpaid", "paid")


def get_by_public_id(db: Session, public_id: UUID) -> Payment | None:
    return db.scalars(select(Payment).where(Payment.public_id == public_id)).first()


def get_by_invoice(db: Session, invoice_number: str) -> Payment | None:
    return (
        db.scalars(select(Payment).where(Payment.invoice_number == invoice_number)).first()
    )


def list_by_booking_id(db: Session, booking_id: int) -> list[Payment]:
    stmt = select(Payment).where(Payment.booking_id == booking_id).order_by(Payment.id)
    return list(db.scalars(stmt).all())


def create_payment(
    db: Session,
    booking_id: int,
    amount: int,
    kind: PaymentKind,
    invoice_number: str,
    provider_request_id: str = "",
) -> Payment:
    payment = Payment(
        booking_id=booking_id,
        amount=amount,
        kind=kind,
        invoice_number=invoice_number,
        provider_request_id=provider_request_id or None,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def mark_paid(db: Session, payment: Payment, note: str = "") -> Payment:
    """Mark paid and auto-confirm a pending booking (deposit rule).

    `note` records something the manager has to act on (e.g. money that arrived
    for a visit that was already cancelled) without lying about the status.
    """
    payment.status = "paid"
    payment.failure_reason = note[:160] or None
    booking = db.get(Booking, payment.booking_id)
    if booking is not None and booking.status == "pending":
        booking.status = "confirmed"
    db.commit()
    db.refresh(payment)
    return payment


def mark_failed(db: Session, payment: Payment, reason: str, provider_status: str = "") -> Payment:
    """The gateway or the clock said no. Only a live payment can fail this way.

    A payment that was already refunded stays refunded — money that went back does
    not become a failure because a late notification arrived.
    """
    if payment.status == "refunded":
        return payment
    payment.status = "failed"
    payment.failure_reason = reason[:160]
    if provider_status:
        payment.provider_status = provider_status[:40]
    db.commit()
    db.refresh(payment)
    return payment


def record_provider_status(db: Session, payment: Payment, provider_status: str) -> Payment:
    """Keep whatever the gateway reported, even when it changes no state."""
    if provider_status:
        payment.provider_status = provider_status[:40]
        db.commit()
        db.refresh(payment)
    return payment


def can_refund(payment: Payment) -> bool:
    return payment.status == "paid"


def mark_refunded(db: Session, payment: Payment, note: str = "") -> Payment:
    payment.status = "refunded"
    payment.refunded_at = datetime.now(UTC)
    payment.failure_reason = note[:160] or None
    db.commit()
    db.refresh(payment)
    return payment


def expire_unpaid_for_booking(db: Session, booking_id: int, reason: str) -> int:
    """Mark the unpaid payments of a dead booking as failed. Returns how many."""
    stmt = select(Payment).where(
        Payment.booking_id == booking_id, Payment.status == "unpaid"
    )
    changed = 0
    for payment in db.scalars(stmt).all():
        payment.status = "failed"
        payment.failure_reason = reason[:160]
        changed += 1
    if changed:
        db.commit()
    return changed


def booking_public_id(db: Session, payment: Payment) -> UUID:
    return db.get(Booking, payment.booking_id).public_id
