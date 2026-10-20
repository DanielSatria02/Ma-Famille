from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.payment import Payment
from app.schemas.payment import PaymentKind
from app.services import notifications as notification_service

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
    checkout_url: str = "",
    provider_token_id: str = "",
) -> Payment:
    payment = Payment(
        booking_id=booking_id,
        amount=amount,
        kind=kind,
        invoice_number=invoice_number,
        provider_request_id=provider_request_id or None,
        checkout_url=checkout_url or None,
        provider_token_id=provider_token_id or None,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def find_unpaid_for_booking(db: Session, booking_id: int) -> Payment | None:
    """The payment still owed for this booking, if there is one.

    One visit has one price. Opening a second invoice for a booking that already
    has an unpaid one leaves the customer with two pages to pay and the venue
    with two amounts to reconcile, and the second invoice is the one that
    actually gets paid.
    """
    return db.scalars(
        select(Payment)
        .where(Payment.booking_id == booking_id, Payment.status == "unpaid")
        .order_by(Payment.id)
    ).first()


def find_unpaid_for_visit(db: Session, booking) -> Payment | None:
    """The invoice still owed for the visit this booking is part of.

    A visit of several hours is one purchase with one invoice, and the invoice
    is raised against the first hour. Looking only at the hour in the request
    meant that opening the second hour's payment page asked the gateway for a
    second invoice — the customer then had two DOKU pages for one booking.
    """
    if booking.group_public_id is None:
        return find_unpaid_for_booking(db, booking.id)
    from app.models.booking import Booking

    booking_ids = select(Booking.id).where(Booking.group_public_id == booking.group_public_id)
    return db.scalars(
        select(Payment)
        .where(Payment.booking_id.in_(booking_ids), Payment.status == "unpaid")
        .order_by(Payment.id)
    ).first()


def mark_paid(db: Session, payment: Payment, note: str = "") -> Payment:
    """Mark paid and auto-confirm the visit (deposit rule).

    `note` records something the manager has to act on (e.g. money that arrived
    for a visit that was already cancelled) without lying about the status.

    The whole visit is confirmed, not only the hour the invoice was raised
    against. A two-hour booking paid in full is two hours of the court; leaving
    the second hour pending would let it expire and be given away while the
    customer had already paid for it.
    """
    payment.status = "paid"
    payment.failure_reason = note[:160] or None
    booking = db.get(Booking, payment.booking_id)
    if booking is not None and booking.status == "pending":
        from app.services import bookings as booking_service

        for row in booking_service.list_group(db, booking.group_public_id):
            if row.status == "pending":
                row.status = "confirmed"
        notification_service.queue_event(
            db, booking_service.list_group(db, booking.group_public_id), "confirmed"
        )
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
