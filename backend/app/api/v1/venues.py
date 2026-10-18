from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.security import require_manager
from app.db.session import get_db
from app.schemas.venue import VenueCreate, VenueResponse, VenueUpdate
from app.schemas.venue_hours import VenueHoursResponse, VenueHoursUpdate
from app.services import hours as hours_service
from app.services import venues as venue_service

router = APIRouter(prefix="/venues", tags=["venues"])


def _to_response(venue) -> VenueResponse:
    return VenueResponse(
        public_id=venue.public_id,
        name=venue.name,
        address=venue.address,
        tags=venue.tags or [],
        lat=venue.lat,
        lng=venue.lng,
        created_at=venue.created_at,
    )


@router.get("", summary="List venues (filter by search or tag)", response_model=list[VenueResponse])
def list_venues(
    q: str | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
) -> list[VenueResponse]:
    return [_to_response(v) for v in venue_service.list_venues(db, q, tag)]


@router.get(
    "/tags",
    summary="Tag vocabulary used by venues",
    response_model=list[str],
)
def list_tags(db: Session = Depends(get_db)) -> list[str]:
    return venue_service.all_tags(db)


@router.post(
    "", summary="Create venue (manager)", response_model=VenueResponse, status_code=201,
    dependencies=[Depends(require_manager)],
)
def create_venue(body: VenueCreate, db: Session = Depends(get_db)) -> VenueResponse:
    return _to_response(venue_service.create_venue(db, body))


@router.get("/{public_id}", summary="Get venue", response_model=VenueResponse)
def get_venue(public_id: UUID, db: Session = Depends(get_db)) -> VenueResponse:
    venue = venue_service.get_by_public_id(db, public_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue not found")
    return _to_response(venue)


@router.patch(
    "/{public_id}",
    summary="Update venue (manager)",
    response_model=VenueResponse,
    dependencies=[Depends(require_manager)],
)
def update_venue(
    public_id: UUID, body: VenueUpdate, db: Session = Depends(get_db)
) -> VenueResponse:
    venue = venue_service.get_by_public_id(db, public_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue not found")
    return _to_response(venue_service.update_venue(db, venue, body))


@router.delete(
    "/{public_id}",
    summary="Delete venue (manager)",
    status_code=204,
    dependencies=[Depends(require_manager)],
)
def delete_venue(public_id: UUID, db: Session = Depends(get_db)) -> None:
    venue = venue_service.get_by_public_id(db, public_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue not found")
    venue_service.delete_venue(db, venue)


def _venue_or_404(db: Session, public_id: UUID):
    venue = venue_service.get_by_public_id(db, public_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue not found")
    return venue


@router.get(
    "/{public_id}/hours",
    summary="Opening hours (7 days, unset days fall back to defaults)",
    response_model=list[VenueHoursResponse],
)
def list_venue_hours(
    public_id: UUID, db: Session = Depends(get_db)
) -> list[VenueHoursResponse]:
    return [
        VenueHoursResponse(**entry)
        for entry in hours_service.list_hours(db, _venue_or_404(db, public_id))
    ]


@router.put(
    "/{public_id}/hours/{day_of_week}",
    summary="Set opening hours for one weekday (manager)",
    response_model=VenueHoursResponse,
    dependencies=[Depends(require_manager)],
)
def update_venue_hours(
    body: VenueHoursUpdate,
    public_id: UUID,
    day_of_week: int = Path(ge=0, le=6, description="0 = Monday ... 6 = Sunday"),
    db: Session = Depends(get_db),
) -> VenueHoursResponse:
    venue = _venue_or_404(db, public_id)
    return VenueHoursResponse(
        **hours_service.upsert_hours(db, venue, day_of_week, body)
    )
