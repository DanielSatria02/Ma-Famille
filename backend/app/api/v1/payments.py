from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.realtime import notify_booking_changed
from app.core.config import settings
from app.core.security import require_manager
from app.db.session import get_db
from app.models.booking import Booking
from app.schemas.payment import (
    DokuWebhookAck,
    PaymentCreate,
    PaymentInitiateResponse,
    PaymentRefundResponse,
    PaymentResponse,
)
from app.services import bookings as booking_service
from app.services import doku
from app.services import payments as payment_service

router = APIRouter(prefix="/payments", tags=["payments"])

WEBHOOK_TARGET = f"{settings.root_path}{settings.api_v1_prefix}/payments/webhook/doku"


def _to_response(db: Session, payment) -> PaymentResponse:
    return PaymentResponse(
        public_id=payment.public_id,
        booking_public_id=payment_service.booking_public_id(db, payment),
        amount=payment.amount,
        kind=payment.kind,
        status=payment.status,
        invoice_number=payment.invoice_number,
        provider_status=payment.provider_status,
        failure_reason=payment.failure_reason,
        refunded_at=payment.refunded_at,
        checkout_url=payment.checkout_url,
        created_at=payment.created_at,
    )


@router.post(
    "",
    summary="Create DOKU checkout (sandbox)",
    response_model=PaymentInitiateResponse,
    responses={501: {"description": "DOKU keys missing"}},
)
def create_payment(body: PaymentCreate, db: Session = Depends(get_db)):
    booking = db.scalars(
        select(Booking).where(Booking.public_id == body.booking_public_id)
    ).first()
    if booking is None:
        raise HTTPException(status_code=404, detail="booking not found")
    # A booking that already owes money keeps the invoice it has. Asking the
    # gateway for another one leaves the customer with two pages to pay and the
    # venue with two amounts to reconcile, and the one nobody was looking at is
    # the one that gets paid.
    existing = payment_service.find_unpaid_for_visit(db, booking)
    if existing is not None and existing.checkout_url:
        return PaymentInitiateResponse(
            invoice_number=existing.invoice_number,
            checkout_url=existing.checkout_url,
            token_id=existing.provider_token_id or "",
        )

    # A visit of several hours is one purchase, so "full" means the whole
    # visit — not whatever the client happened to know about. The client that
    # only had the first hour of a two-hour booking would otherwise charge
    # for one hour and confirm one, and the second hour would be given away.
    amount = body.amount
    if body.kind == "full":
        amount = max(body.amount, booking_service.group_span(db, booking)["group_total"])
    else:
        # A deposit cannot be more than the visit is worth.
        amount = min(body.amount, booking_service.group_span(db, booking)["group_total"])

    invoice_number = doku.new_invoice_number()
    try:
        result = doku.create_checkout(
            invoice_number=invoice_number,
            amount=amount,
            customer_name=booking.customer_name,
        )
    except doku.DokuError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        ) from exc
    payment = payment_service.create_payment(
        db,
        booking_id=booking.id,
        amount=amount,
        kind=body.kind,
        invoice_number=invoice_number,
        provider_request_id=getattr(result, "request_id", ""),
        checkout_url=result.checkout_url,
        provider_token_id=result.token_id,
    )
    return PaymentInitiateResponse(
        invoice_number=payment.invoice_number,
        checkout_url=payment.checkout_url or "",
        token_id=payment.provider_token_id or "",
    )


@router.get("", summary="List payments per booking")
def list_payments(
    booking_public_id: UUID, db: Session = Depends(get_db)
) -> list[PaymentResponse]:
    booking = db.scalars(
        select(Booking).where(Booking.public_id == booking_public_id)
    ).first()
    if booking is None:
        raise HTTPException(status_code=404, detail="booking not found")
    payments = payment_service.list_by_booking_id(db, booking.id)
    return [_to_response(db, p) for p in payments]


@router.post(
    "/{public_id}/mark-paid",
    summary="Mark payment paid (manager)",
    dependencies=[Depends(require_manager)],
)
def mark_paid(public_id: UUID, db: Session = Depends(get_db)) -> PaymentResponse:
    payment = payment_service.get_by_public_id(db, public_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment not found")
    paid = payment_service.mark_paid(db, payment)
    notify_booking_changed(db.get(Booking, paid.booking_id))
    return _to_response(db, paid)


@router.post(
    "/{public_id}/refund",
    summary="Refund a paid payment (manager)",
    response_model=PaymentRefundResponse,
    dependencies=[Depends(require_manager)],
    responses={
        409: {"description": "Only a paid payment can be refunded"},
        502: {"description": "The provider refused the refund"},
    },
)
def refund(public_id: UUID, db: Session = Depends(get_db)) -> PaymentRefundResponse:
    payment = payment_service.get_by_public_id(db, public_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment not found")
    if not payment_service.can_refund(payment):
        raise HTTPException(
            status_code=409,
            detail=f"a {payment.status} payment cannot be refunded",
        )
    if not settings.doku_configured:
        # No keys: never claim money moved. Book it and say who has to move it.
        refunded = payment_service.mark_refunded(
            db, payment, note="refunded without a gateway: no DOKU keys configured"
        )
        notify_booking_changed(db.get(Booking, refunded.booking_id))
        return PaymentRefundResponse(
            payment=_to_response(db, refunded),
            provider="local",
            detail=(
                "no DOKU keys configured — the payment is marked refunded here, "
                "the money itself has to be returned by hand"
            ),
        )
    try:
        result = doku.request_refund(
            invoice_number=payment.invoice_number or "",
            original_request_id=payment.provider_request_id or "",
            amount=payment.amount,
        )
    except doku.DokuError as exc:
        # Nothing changed locally: the payment is still paid until DOKU says otherwise.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if result.status != "SUCCESS":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DOKU refused the refund ({result.status}): {result.message}",
        )
    refunded = payment_service.mark_refunded(
        db, payment, note=f"{result.kind} {result.approval_code}".strip()
    )
    payment_service.record_provider_status(db, refunded, "REFUNDED")
    notify_booking_changed(db.get(Booking, refunded.booking_id))
    return PaymentRefundResponse(
        payment=_to_response(db, refunded),
        provider="doku",
        detail=result.message or f"DOKU {result.kind or 'refund'} accepted",
        provider_status="REFUNDED",
    )


def _webhook_status(body: dict) -> tuple[str, str, str]:
    """(invoice, mapped status, raw status)."""
    try:
        invoice = body["order"]["invoice_number"]
    except (KeyError, TypeError):
        raise HTTPException(status_code=422, detail="missing order.invoice_number")
    raw_status = ""
    try:
        raw_status = str(body["transaction"]["status"]).upper()
    except (KeyError, TypeError):
        pass
    if raw_status == "SUCCESS":
        mapped = "paid"
    elif raw_status in ("FAILED", "EXPIRED", "CANCELLED"):
        mapped = "failed"
    else:
        mapped = "pending"
    return invoice, mapped, raw_status


@router.post(
    "/webhook/doku",
    summary="DOKU HTTP notification (sandbox)",
    response_model=DokuWebhookAck,
    responses={401: {"description": "Bad signature"}},
)
async def doku_webhook(request: Request, db: Session = Depends(get_db)):
    if not settings.doku_configured:
        raise HTTPException(status_code=501, detail="DOKU keys not configured")
    raw = await request.body()
    headers = request.headers
    ok = doku.verify_signature(
        signature=headers.get("signature", ""),
        client_id=headers.get("client-id", ""),
        request_id=headers.get("request-id", ""),
        timestamp=headers.get("request-timestamp", ""),
        request_target=WEBHOOK_TARGET,
        digest=doku.build_digest(raw),
        secret=settings.doku_secret_key,
    )
    if not ok:
        raise HTTPException(status_code=401, detail="bad DOKU signature")
    try:
        body = dict(await request.json())
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid JSON body")
    invoice, mapped, raw_status = _webhook_status(body)
    payment = payment_service.get_by_invoice(db, invoice)
    if payment is None:
        raise HTTPException(status_code=404, detail="unknown invoice")
    detail = "matched"
    if mapped == "paid":
        booking = _booking_of(db, payment)
        if booking is not None and booking.status in ("cancelled", "expired"):
            # Money arrived for a visit that no longer holds its hours: keep the
            # truth (it is paid) and leave a note so a manager refunds it.
            payment_service.record_provider_status(db, payment, raw_status)
            payment_service.mark_paid(
                db, payment, note="paid after the visit was cancelled — refund it"
            )
            detail = "paid after the visit was cancelled: a refund is needed"
        else:
            payment_service.record_provider_status(db, payment, raw_status)
            payment_service.mark_paid(db, payment)
    elif mapped == "failed":
        payment_service.mark_failed(db, payment, f"gateway reported {raw_status}", raw_status)
        detail = "recorded as failed"
    else:
        payment_service.record_provider_status(db, payment, raw_status)
        detail = f"recorded as {raw_status or 'unknown'}"
    # Tell whoever is watching this booking, rather than making their page
    # ask again in a few seconds to find out what this line already knows.
    notify_booking_changed(_booking_of(db, payment))
    return DokuWebhookAck(
        invoice_number=invoice, payment_status=payment.status, detail=detail
    )


def _booking_of(db: Session, payment):
    return db.get(Booking, payment.booking_id)
