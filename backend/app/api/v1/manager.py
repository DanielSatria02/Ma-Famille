from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import require_manager
from app.db.session import get_db
from app.schemas.booking import BookingResponse
from app.schemas.manager import OccupancyPoint
from app.services import bookings as booking_service
from app.services import manager as manager_service

router = APIRouter(
    prefix="/manager", tags=["manager"], dependencies=[Depends(require_manager)]
)

MAX_RANGE_DAYS = 93


@router.get("/bookings", summary="Incoming bookings by start time (manager)")
def incoming_bookings(
    booking_status: str | None = None,
    day: date | None = None,
    from_day: date | None = None,
    to_day: date | None = None,
    db: Session = Depends(get_db),
):
    if from_day is not None and to_day is not None:
        if to_day < from_day:
            raise HTTPException(status_code=422, detail="to_day before from_day")
        if (to_day - from_day).days > MAX_RANGE_DAYS:
            raise HTTPException(
                status_code=422, detail=f"range too wide (max {MAX_RANGE_DAYS} days)"
            )
    bookings = manager_service.incoming_bookings(
        db,
        booking_status=booking_status,
        day=day,
        from_day=from_day,
        to_day=to_day,
    )
    return [
        BookingResponse(
            public_id=b.public_id,
            slot_public_id=booking_service.slot_public_id(db, b),
            group_public_id=b.group_public_id,
            customer_name=b.customer_name,
            customer_contact=b.customer_contact,
            status=b.status,
            created_at=b.created_at,
            **booking_service.detail(db, b),
        )
        for b in bookings
    ]


@router.get("/occupancy", summary="Occupancy summary for chart (manager)")
def occupancy(
    from_day: date, to_day: date, db: Session = Depends(get_db)
) -> list[OccupancyPoint]:
    if to_day < from_day:
        raise HTTPException(status_code=422, detail="to_day before from_day")
    if (to_day - from_day).days > 93:
        raise HTTPException(status_code=422, detail="range too wide (max 93 days)")
    return [
        OccupancyPoint(**point)
        for point in manager_service.occupancy(db, from_day, to_day)
    ]
