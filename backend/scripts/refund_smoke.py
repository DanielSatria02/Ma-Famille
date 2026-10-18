"""Live check of the refund endpoint against the dev stack (Postgres).

    .venv/bin/python backend/scripts/refund_smoke.py
"""

import json

import httpx
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.booking import Booking
from app.services import payments as payment_service

API = "http://localhost:8000/v1"

with SessionLocal() as db:
    booking = db.scalars(
        select(Booking).where(Booking.status != "cancelled").order_by(Booking.id.desc())
    ).first()
    if booking is None:
        raise SystemExit("no live booking in the dev database")
    payment = payment_service.create_payment(
        db,
        booking_id=booking.id,
        amount=75000,
        kind="deposit",
        invoice_number="MAF-DEVCHECK-1",
        provider_request_id="req-devcheck",
    )
    payment_service.mark_paid(db, payment)
    public_id = payment.public_id
    print(f"booking {booking.public_id} → paid payment {public_id}")

first = httpx.post(f"{API}/payments/{public_id}/refund", timeout=20)
print("refund 1:", first.status_code, json.dumps(first.json())[:400])

second = httpx.post(f"{API}/payments/{public_id}/refund", timeout=20)
print("refund 2:", second.status_code, json.dumps(second.json())[:200])

listed = httpx.get(
    f"{API}/payments", params={"booking_public_id": str(booking.public_id)}, timeout=20
).json()
row = [p for p in listed if p["public_id"] == str(public_id)][0]
print("stored:", {k: row[k] for k in ("status", "failure_reason", "refunded_at")})
