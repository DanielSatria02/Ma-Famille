"""Promo codes: find one, check it may be used, and take money off.

A code is refused for a reason a customer can act on — unknown, inactive, not
started yet, expired, out of uses, or for another venue — never a silent no-op.
The discount is computed against a gross total and never exceeds it, so a code
cannot make a booking cost less than zero.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.court import Court
from app.models.promotion import Promotion


class PromoError(Exception):
    """A code was sent but cannot be applied; the message is shown to the client."""


def normalise_code(code: str) -> str:
    """Codes are case-insensitive: `hemat` and `HEMAT` are one voucher."""
    return (code or "").strip().upper()


def find_by_code(db: Session, code: str) -> Promotion | None:
    return db.scalar(
        select(Promotion).where(Promotion.code == normalise_code(code))
    )


def discount_for(promo: Promotion, gross: int) -> int:
    """Rupiah to take off `gross`. Capped at the gross, so it never goes negative."""
    if gross <= 0:
        return 0
    if promo.kind == "amount":
        amount = promo.value
    else:
        amount = gross * min(promo.value, 100) // 100
    return max(0, min(amount, gross))


def _naive(value: datetime) -> datetime:
    """Wall time, matching every other service here.

    Postgres returns `valid_from`/`valid_to` tz-aware while `now` is UTC, so
    comparing them raw raises TypeError and a stale code 500s instead of being
    refused. Strip both to UTC wall time — same rule as slots and pricing.
    """
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def validate(
    db: Session,
    promo: Promotion,
    court: Court | None,
    now: datetime | None = None,
) -> None:
    """Raise PromoError when this code may not be used for that court right now."""
    now = _naive(now or datetime.now(UTC))
    if not promo.is_active:
        raise PromoError("that code is no longer active")
    if promo.valid_from is not None and now < _naive(promo.valid_from):
        raise PromoError("that code is not active yet")
    if promo.valid_to is not None and now > _naive(promo.valid_to):
        raise PromoError("that code has expired")
    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        raise PromoError("that code has been used the maximum number of times")
    # A scoped code only works for its own venue; an unscoped one works anywhere.
    if (
        promo.venue_id is not None
        and court is not None
        and promo.venue_id != court.venue_id
    ):
        raise PromoError("that code is only valid for a different venue")


def apply(
    db: Session,
    code: str,
    court: Court,
    gross: int,
    now: datetime | None = None,
) -> tuple[Promotion, int]:
    """Validate `code` against `court` and return (promo, discount).

    Raises PromoError for any refusal. Does not commit — the caller owns the
    transaction so the usage count and the booking land together or not at all.
    """
    promo = find_by_code(db, code)
    if promo is None:
        raise PromoError("that code does not exist")
    validate(db, promo, court, now=now)
    return promo, discount_for(promo, gross)


def redeem(db: Session, promo: Promotion) -> None:
    """Count one use. Committed by the caller with the booking it paid for."""
    promo.used_count += 1
    db.flush()
