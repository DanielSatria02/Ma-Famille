from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_manager
from app.db.session import get_db
from app.schemas.booking import (
    BookingCreate,
    BookingRangeCreate,
    BookingRangeResponse,
    BookingResponse,
)
from app.services import bookings as booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _to_response(db: Session, booking) -> BookingResponse:
    return BookingResponse(
        public_id=booking.public_id,
        slot_public_id=booking_service.slot_public_id(db, booking),
        group_public_id=booking.group_public_id,
        customer_name=booking.customer_name,
        customer_contact=booking.customer_contact,
        status=booking.status,
        created_at=booking.created_at,
        **booking_service.detail(db, booking),
    )


@router.post(
    "",
    summary="Book a slot (409 on conflict)",
    status_code=201,
    responses={409: {"description": "Slot already booked"}},
)
def create_booking(body: BookingCreate, db: Session = Depends(get_db)) -> BookingResponse:
    try:
        booking = booking_service.create_booking(db, body)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="slot already booked")
    except booking_service.SlotUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if booking is None:
        raise HTTPException(status_code=404, detail="slot not found")
    return _to_response(db, booking)


@router.get("", summary="Customer booking history")
def list_my_bookings(customer_contact: str, db: Session = Depends(get_db)):
    bookings = booking_service.list_by_contact(db, customer_contact)
    return [_to_response(db, b) for b in bookings]


@router.post(
    "/range",
    summary="Book consecutive hours on one court (409 on conflict)",
    status_code=201,
    response_model=BookingRangeResponse,
    responses={
        409: {"description": "One of the hours is taken"},
        422: {"description": "Range not whole hours, or lead time not met"},
    },
)
def create_range_booking(
    body: BookingRangeCreate, db: Session = Depends(get_db)
) -> BookingRangeResponse:
    try:
        result = booking_service.create_range_booking(db, body)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="slot already booked")
    except booking_service.SlotUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except booking_service.LeadTimeViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="court not found")
    return BookingRangeResponse(
        group_public_id=result["group_public_id"],
        hours=result["hours"],
        total=result["total"],
        bookings=[_to_response(db, b) for b in result["bookings"]],
    )


@router.post(
    "/groups/{group_public_id}/cancel",
    summary="Cancel every booking of a group",
    response_model=list[BookingResponse],
)
def cancel_group(
    group_public_id: UUID, db: Session = Depends(get_db)
) -> list[BookingResponse]:
    bookings = booking_service.cancel_group(db, group_public_id)
    if not bookings:
        raise HTTPException(status_code=404, detail="booking group not found")
    return [_to_response(db, b) for b in bookings]


@router.get("/{public_id}", summary="Get booking")
def get_booking(public_id: UUID, db: Session = Depends(get_db)) -> BookingResponse:
    booking = booking_service.get_by_public_id(db, public_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="booking not found")
    return _to_response(db, booking)


@router.post(
    "/{public_id}/confirm",
    summary="Confirm booking (deposit/manager)",
    dependencies=[Depends(require_manager)],
)
def confirm_booking(public_id: UUID, db: Session = Depends(get_db)) -> BookingResponse:
    booking = booking_service.get_by_public_id(db, public_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="booking not found")
    confirmed = booking_service.confirm_booking(db, booking)
    if confirmed is None:
        raise HTTPException(status_code=409, detail="booking is cancelled")
    return _to_response(db, confirmed)


@router.post("/{public_id}/cancel", summary="Cancel booking")
def cancel_booking(public_id: UUID, db: Session = Depends(get_db)) -> BookingResponse:
    booking = booking_service.get_by_public_id(db, public_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="booking not found")
    return _to_response(db, booking_service.cancel_booking(db, booking))
