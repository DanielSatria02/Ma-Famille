from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.court import CourtKind
from app.schemas.facility import FacilityResponse
from app.services import facilities as facility_service

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get(
    "",
    summary="Bookable facilities for the client picker",
    response_model=list[FacilityResponse],
)
def list_facilities(
    venue_public_id: UUID | None = None,
    kind: CourtKind | None = None,
    db: Session = Depends(get_db),
) -> list[FacilityResponse]:
    entries = facility_service.list_facilities(db, venue_public_id, kind)
    if entries is None:
        raise HTTPException(status_code=404, detail="club not found")
    return [FacilityResponse(**entry) for entry in entries]
