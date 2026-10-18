from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.paging import Page, set_total
from app.core.security import require_manager
from app.db.session import get_db
from app.schemas.booking import BookingResponse
from app.schemas.court import CourtKind
from app.schemas.facility import ManagerFacilityResponse
from app.schemas.manager import ManagerStats, OccupancyPoint
from app.schemas.notification import NotificationDispatchResult, NotificationResponse
from app.services import bookings as booking_service
from app.services import facilities as facility_service
from app.services import manager as manager_service
from app.services import notifications as notification_service

router = APIRouter(
    prefix="/manager", tags=["manager"], dependencies=[Depends(require_manager)]
)

MAX_RANGE_DAYS = 93


@router.get("/bookings", summary="Incoming bookings by start time (manager, paged)")
def incoming_bookings(
    booking_status: str | None = None,
    day: date | None = None,
    from_day: date | None = None,
    to_day: date | None = None,
    page: Page = Depends(),
    response: Response = None,
    db: Session = Depends(get_db),
):
    if from_day is not None and to_day is not None:
        if to_day < from_day:
            raise HTTPException(status_code=422, detail="to_day before from_day")
        if (to_day - from_day).days > MAX_RANGE_DAYS:
            raise HTTPException(
                status_code=422, detail=f"range too wide (max {MAX_RANGE_DAYS} days)"
            )
    filters = {
        "booking_status": booking_status,
        "day": day,
        "from_day": from_day,
        "to_day": to_day,
    }
    bookings = manager_service.incoming_bookings(
        db, **filters, limit=page.limit, offset=page.offset
    )
    set_total(response, manager_service.count_incoming(db, **filters))
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
    if (to_day - from_day).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422, detail=f"range too wide (max {MAX_RANGE_DAYS} days)"
        )
    return [
        OccupancyPoint(**point)
        for point in manager_service.occupancy(db, from_day, to_day)
    ]


@router.get("/stats", summary="Dashboard counters (manager)", response_model=ManagerStats)
def stats(
    day: date | None = None,
    week_start: date | None = None,
    db: Session = Depends(get_db),
) -> ManagerStats:
    """Counters for the manager dashboard. `day` defaults to today; the week
    runs Monday-Sunday around it unless `week_start` says otherwise."""
    target = day if day is not None else date.today()
    if week_start is not None and week_start > target:
        raise HTTPException(status_code=422, detail="week_start after day")
    return ManagerStats(**manager_service.stats(db, target, week_start))


@router.get(
    "/facilities",
    summary="Facilities with live status and rates (manager)",
    response_model=list[ManagerFacilityResponse],
)
def facilities(
    venue_public_id: UUID | None = None,
    kind: CourtKind | None = None,
    db: Session = Depends(get_db),
) -> list[ManagerFacilityResponse]:
    entries = facility_service.list_facilities(
        db, venue_public_id, kind, manager_view=True
    )
    if entries is None:
        raise HTTPException(status_code=404, detail="venue not found")
    return [ManagerFacilityResponse(**entry) for entry in entries]


@router.get(
    "/notifications",
    summary="Guest messages queued for this venue (manager, paged)",
    response_model=list[NotificationResponse],
)
def notifications(
    status: str | None = None,
    page: Page = Depends(),
    response: Response = None,
    db: Session = Depends(get_db),
) -> list[NotificationResponse]:
    """The outbox: what the venue has told (or still owes) its guests.

    `status=queued` shows what a dispatch would work on next.
    """
    if status is not None and status not in ("queued", "sent", "logged", "failed"):
        raise HTTPException(status_code=422, detail="unknown status")
    rows = notification_service.list_notifications(
        db, status, limit=page.limit, offset=page.offset
    )
    set_total(response, notification_service.count_notifications(db, status))
    return [
        NotificationResponse(
            public_id=row.public_id,
            event=row.event,
            channel=row.channel,
            recipient=row.recipient,
            subject=row.subject,
            body=row.body,
            status=row.status,
            transport=row.transport,
            error=row.error,
            attempts=row.attempts,
            sent_at=row.sent_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post(
    "/notifications/dispatch",
    summary="Send the queued guest messages (manager)",
    response_model=NotificationDispatchResult,
)
def dispatch_notifications(
    limit: int = 20, db: Session = Depends(get_db)
) -> NotificationDispatchResult:
    """Run the queue through the configured transport once.

    With the default `NOTIFY_TRANSPORT=log` nothing is delivered: the messages are
    recorded and reported as `logged`.
    """
    return NotificationDispatchResult(
        **notification_service.dispatch_pending(db, max(min(limit, 100), 1))
    )
