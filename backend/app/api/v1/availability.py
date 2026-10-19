from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.court import Court
from app.models.venue import Venue
from app.schemas.availability import DayAvailability, DayHoursResponse
from app.services import availability as availability_service

router = APIRouter(prefix="/availability", tags=["availability"])

MAX_RANGE_DAYS = 93


def _court_or_404(db: Session, public_id: UUID) -> Court:
    court = db.scalars(select(Court).where(Court.public_id == public_id)).first()
    if court is None:
        raise HTTPException(status_code=404, detail="court not found")
    return court


@router.get(
    "/hours",
    summary="Opening hours of one day with a status per hour",
    response_model=DayHoursResponse,
)
def hours_of_day(
    court_public_id: UUID, day: date, db: Session = Depends(get_db)
) -> DayHoursResponse:
    court = _court_or_404(db, court_public_id)
    return DayHoursResponse(**availability_service.day_hours(db, court, day))


@router.get(
    "/dates",
    summary="Per-day availability roll-up for a calendar range",
    response_model=list[DayAvailability],
)
def dates(
    court_public_id: UUID | None = None,
    venue_public_id: UUID | None = None,
    from_day: date = Query(...),
    to_day: date = Query(...),
    db: Session = Depends(get_db),
) -> list[DayAvailability]:
    if to_day < from_day:
        raise HTTPException(status_code=422, detail="to_day before from_day")
    if (to_day - from_day).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422, detail=f"range too wide (max {MAX_RANGE_DAYS} days)"
        )
    if court_public_id is not None:
        court = _court_or_404(db, court_public_id)
        points = availability_service.date_summary(db, court, from_day, to_day)
    elif venue_public_id is not None:
        venue = db.scalars(select(Venue).where(Venue.public_id == venue_public_id)).first()
        if venue is None:
            raise HTTPException(status_code=404, detail="venue not found")
        points = availability_service.venue_date_summary(db, venue, from_day, to_day)
    else:
        raise HTTPException(
            status_code=422, detail="court_public_id or venue_public_id is required"
        )
    return [DayAvailability(**point) for point in points]
