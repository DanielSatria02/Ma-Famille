from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, Security
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.paging import Page, set_total
from app.core.config import settings
from app.core.security import is_manager, manager_token_header, require_manager
from app.db.session import get_db
from app.schemas.booking import (
    BookingCreate,
    BookingRangeCreate,
    BookingRangeResponse,
    BookingResponse,
)
from app.services import bookings as booking_service
from app.services import customers as customer_service
from app.services import promotions as promo_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _signed_in_customer(
    db: Session = Depends(get_db),
    x_customer_token: str | None = Header(default=None, alias="X-Customer-Token"),
):
    """The account behind `X-Customer-Token`, or None.

    None is a normal answer, not an error: a walk-up booking without an
    account is still a booking. An expired or unknown token is treated the
    same way rather than failing the request — the booking does not depend
    on it, and refusing would punish someone for a stale browser tab.
    """
    return customer_service.customer_for_token(db, x_customer_token)


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
def create_booking(
    body: BookingCreate,
    customer=Depends(_signed_in_customer),
    db: Session = Depends(get_db),
) -> BookingResponse:
    try:
        booking = booking_service.create_booking(
            db, body, customer_id=customer.id if customer else None
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="slot already booked")
    except booking_service.SlotUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except promo_service.PromoError as exc:
        # The code was refused for a reason the customer can act on (expired,
        # other venue, maxed out). Nothing was written.
        raise HTTPException(status_code=422, detail=str(exc))
    if booking is None:
        raise HTTPException(status_code=404, detail="slot not found")
    return _to_response(db, booking)


@router.get("", summary="Customer booking history (paged, newest first)")
def list_my_bookings(
    customer_contact: str | None = Query(default=None, min_length=3),
    customer=Depends(_signed_in_customer),
    page: Page = Depends(),
    response: Response = None,
    db: Session = Depends(get_db),
):
    """A signed-in customer gets their account's bookings; otherwise the
    contact has to be named.

    The account list is the one that cannot be split by a typo, so it wins
    when both are present — the contact is only there to carry the lookup
    for a booking made without an account.
    """
    if customer is not None:
        rows = booking_service.list_by_customer(
            db, customer.id, limit=page.limit, offset=page.offset
        )
        set_total(response, booking_service.count_by_customer(db, customer.id))
        return [_to_response(db, b) for b in rows]
    if not customer_contact:
        raise HTTPException(
            status_code=422,
            detail="Sign in, or give the contact the booking was made with.",
        )
    bookings = booking_service.list_by_contact(
        db, customer_contact, limit=page.limit, offset=page.offset
    )
    set_total(response, booking_service.count_by_contact(db, customer_contact))
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
    body: BookingRangeCreate,
    customer=Depends(_signed_in_customer),
    db: Session = Depends(get_db),
) -> BookingRangeResponse:
    try:
        result = booking_service.create_range_booking(
            db, body, customer_id=customer.id if customer else None
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="slot already booked")
    except booking_service.SlotUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except booking_service.LeadTimeViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except promo_service.PromoError as exc:
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
    summary="Cancel every booking of a group (manager or the customer)",
    response_model=list[BookingResponse],
)
def cancel_group(
    group_public_id: UUID,
    customer_contact: str | None = Query(default=None, min_length=3),
    token: str | None = Security(manager_token_header),
    customer=Depends(_signed_in_customer),
    db: Session = Depends(get_db),
) -> list[BookingResponse]:
    existing = booking_service.list_group(db, group_public_id)
    if not existing:
        raise HTTPException(status_code=404, detail="booking group not found")
    # A manager may cancel anything. A customer only their own visit, and the
    # account they booked with counts as proof — that is the point of having
    # one: it cannot be faked by typing the right number.
    owns_by_account = customer is not None and any(
        booking.customer_id == customer.id for booking in existing
    )
    if not is_manager(token, db=db) and not owns_by_account and not booking_service.contact_matches(
        customer_contact, existing
    ):
        raise HTTPException(
            status_code=403,
            detail="manager token or the booking contact is required",
        )
    return [_to_response(db, b) for b in booking_service.cancel_group(db, group_public_id)]


@router.post(
    "/groups/{group_public_id}/confirm",
    summary="Confirm every booking of a group (manager)",
    response_model=list[BookingResponse],
    dependencies=[Depends(require_manager)],
)
def confirm_group(
    group_public_id: UUID, db: Session = Depends(get_db)
) -> list[BookingResponse]:
    if not booking_service.list_group(db, group_public_id):
        raise HTTPException(status_code=404, detail="booking group not found")
    confirmed = booking_service.confirm_group(db, group_public_id)
    if not confirmed:
        raise HTTPException(status_code=409, detail="booking group is cancelled")
    return [_to_response(db, b) for b in confirmed]


@router.get("/{public_id}", summary="Get booking")
def get_booking(public_id: UUID, db: Session = Depends(get_db)) -> BookingResponse:
    # Reading is a place the lazy sweep belongs: an abandoned pending booking
    # must not look alive to a client polling its status.
    booking_service.expire_stale_bookings(db, settings.booking_ttl_minutes)
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


@router.post(
    "/{public_id}/cancel",
    summary="Cancel booking (manager or the customer)",
)
def cancel_booking(
    public_id: UUID,
    customer_contact: str | None = Query(default=None, min_length=3),
    token: str | None = Security(manager_token_header),
    db: Session = Depends(get_db),
) -> BookingResponse:
    booking = booking_service.get_by_public_id(db, public_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="booking not found")
    if not is_manager(token, db=db) and not booking_service.contact_matches(
        customer_contact, [booking]
    ):
        raise HTTPException(
            status_code=403,
            detail="manager token or the booking contact is required",
        )
    return _to_response(db, booking_service.cancel_booking(db, booking))
