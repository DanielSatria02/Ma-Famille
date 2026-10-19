from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.paging import Page, set_total
from app.core.security import require_manager
from app.db.session import get_db
from app.models.court import Court
from app.models.promotion import Promotion
from app.models.venue import Venue
from app.schemas.promotion import (
    PromotionCheck,
    PromotionCreate,
    PromotionResponse,
    PromotionUpdate,
)
from app.services import pricing as pricing_service
from app.services import promotions as promo_service

router = APIRouter(prefix="/promotions", tags=["promotions"])

# Writing codes hands out money, so every manager route here is guarded. The
# public `check` is deliberately open: a customer must be able to test a code
# before they commit to a booking.
MANAGER = [Depends(require_manager)]


def _to_response(promo: Promotion, db: Session) -> PromotionResponse:
    venue = db.get(Venue, promo.venue_id) if promo.venue_id else None
    return PromotionResponse(
        public_id=promo.public_id,
        code=promo.code,
        kind=promo.kind,
        value=promo.value,
        valid_from=promo.valid_from,
        valid_to=promo.valid_to,
        max_uses=promo.max_uses,
        used_count=promo.used_count,
        is_active=promo.is_active,
        venue_public_id=venue.public_id if venue else None,
        created_at=promo.created_at,
    )


@router.get(
    "",
    summary="List promo codes (manager, paged)",
    response_model=list[PromotionResponse],
    dependencies=MANAGER,
)
def list_promotions(
    page: Page = Depends(),
    response: Response = None,
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(Promotion).order_by(Promotion.id.desc()).offset(page.offset).limit(page.limit)
    ).all()
    set_total(response, len(list(db.scalars(select(Promotion)).all())))
    return [_to_response(r, db) for r in rows]


@router.post(
    "",
    summary="Create a promo code (manager)",
    status_code=201,
    dependencies=MANAGER,
)
def create_promotion(body: PromotionCreate, db: Session = Depends(get_db)):
    # A code is the customer-facing handle, so a duplicate is a 409, not a
    # silent second row that would never be reachable by its own code.
    if promo_service.find_by_code(db, body.code) is not None:
        raise HTTPException(status_code=409, detail="that code already exists")
    venue_id = None
    if body.venue_public_id is not None:
        venue = db.scalars(
            select(Venue).where(Venue.public_id == body.venue_public_id)
        ).first()
        if venue is None:
            raise HTTPException(status_code=404, detail="club not found")
        venue_id = venue.id
    promo = Promotion(
        code=body.code,
        kind=body.kind,
        value=body.value,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        max_uses=body.max_uses,
        is_active=body.is_active,
        venue_id=venue_id,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)
    return _to_response(promo, db)


@router.patch(
    "/{public_id}",
    summary="Update a promo code (manager)",
    dependencies=MANAGER,
)
def update_promotion(public_id: UUID, body: PromotionUpdate, db: Session = Depends(get_db)):
    promo = db.scalars(select(Promotion).where(Promotion.public_id == public_id)).first()
    if promo is None:
        raise HTTPException(status_code=404, detail="promo not found")
    provided = body.model_fields_set
    if body.kind is not None and "kind" in provided:
        promo.kind = body.kind
    if body.value is not None and "value" in provided:
        promo.value = body.value
    if "valid_from" in provided:
        promo.valid_from = body.valid_from
    if "valid_to" in provided:
        promo.valid_to = body.valid_to
    if "max_uses" in provided:
        promo.max_uses = body.max_uses
    if body.is_active is not None and "is_active" in provided:
        promo.is_active = body.is_active
    db.commit()
    db.refresh(promo)
    return _to_response(promo, db)


@router.delete(
    "/{public_id}",
    summary="Delete a promo code (manager)",
    status_code=204,
    dependencies=MANAGER,
)
def delete_promotion(public_id: UUID, db: Session = Depends(get_db)):
    promo = db.scalars(select(Promotion).where(Promotion.public_id == public_id)).first()
    if promo is None:
        raise HTTPException(status_code=404, detail="promo not found")
    # Deleting a code that was already redeemed would erase the reason a past
    # booking was cheaper, so only unused codes may be removed outright.
    if promo.used_count > 0:
        raise HTTPException(
            status_code=409,
            detail="that code has been redeemed; deactivate it instead of deleting",
        )
    db.delete(promo)
    db.commit()


@router.get(
    "/check",
    summary="Does this code apply to this court right now? (public)",
    response_model=PromotionCheck,
)
def check_promotion(
    code: str = Query(min_length=1, max_length=40),
    court_public_id: UUID | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    db: Session = Depends(get_db),
):
    """Dry-run a code the way the booking would price it.

    No row is written and the use count is untouched — this is the check the
    client runs before it commits, so a refusal here must match a refusal at
    booking time.
    """
    promo = promo_service.find_by_code(db, code)
    if promo is None:
        return PromotionCheck(ok=False, reason="that code does not exist")

    court = None
    gross = 0
    if court_public_id is not None:
        court = db.scalars(select(Court).where(Court.public_id == court_public_id)).first()
        if court is None:
            return PromotionCheck(ok=False, reason="court not found")
        if starts_at is not None and ends_at is not None and ends_at > starts_at:
            quote = pricing_service.quote(db, court, starts_at, ends_at)
            gross = quote["total"]

    try:
        promo_service.validate(db, promo, court)
    except promo_service.PromoError as exc:
        return PromotionCheck(ok=False, code=promo.code, reason=str(exc))

    discount = promo_service.discount_for(promo, gross)
    return PromotionCheck(
        ok=True,
        code=promo.code,
        discount=discount,
        gross=gross,
        amount_due=max(0, gross - discount),
    )
