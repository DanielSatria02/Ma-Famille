from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.court import Court
from app.schemas.pricing import PricingQuote
from app.services import pricing as pricing_service

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.get(
    "/quote",
    summary="Price and bookability of a whole-hour range",
    response_model=PricingQuote,
)
def quote(
    court_public_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    db: Session = Depends(get_db),
) -> PricingQuote:
    if ends_at <= starts_at:
        raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    if starts_at.date() != ends_at.date():
        raise HTTPException(status_code=422, detail="a quote cannot span two days")
    for label, moment in (("starts_at", starts_at), ("ends_at", ends_at)):
        if moment.minute or moment.second or moment.microsecond:
            raise HTTPException(status_code=422, detail=f"{label} must be a whole hour")

    court = db.scalars(select(Court).where(Court.public_id == court_public_id)).first()
    if court is None:
        raise HTTPException(status_code=404, detail="court not found")
    return PricingQuote(**pricing_service.quote(db, court, starts_at, ends_at))
