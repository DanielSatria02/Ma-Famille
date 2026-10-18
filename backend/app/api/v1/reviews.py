"""Ratings left after a visit.

A rating is public — anyone can read what visitors thought of a venue — but
writing one has to be earned: the caller must have a booking at that venue
whose slot has already started and was not cancelled. A signed-in customer
proves that with `X-Customer-Token`; a visitor without an account proves it
with the contact they booked with, the same way they cancel.

Reading is deliberately open. Gating the list behind a token would mean a
prospective customer could not see the reputation they came to check.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.paging import Page, set_total
from app.db.session import get_db
from app.models.customer import Customer
from app.schemas.review import ReviewCreate, ReviewResponse, VenueRatingResponse
from app.services import customers as customer_service
from app.services import reviews as review_service
from app.services.reviews import ReviewError

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _token_from_header(x_customer_token: str | None) -> str | None:
    return x_customer_token.strip() or None if x_customer_token else None


def optional_customer(
    db: Session = Depends(get_db),
    x_customer_token: str | None = Header(default=None, alias="X-Customer-Token"),
) -> Customer | None:
    """The signed-in customer, or None.

    Unlike `current_customer` this never 401s: a walk-up visitor rates with
    their contact, so an absent or stale token must not stop them. It is only
    a stronger form of proof when it is present.
    """
    return customer_service.customer_for_token(db, _token_from_header(x_customer_token))


def _contact_from_header(
    customer_contact: str | None = Query(default=None, max_length=60),
) -> str:
    return (customer_contact or "").strip()


def _to_response(review, *, mine: bool = False) -> ReviewResponse:
    return ReviewResponse(
        public_id=review.public_id,
        venue_public_id=review.venue.public_id if review.venue else None,
        author=review_service.author_name(review),
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
        mine=mine,
    )


@router.post("", status_code=201, summary="Rate a venue after a visit")
def write_review(
    body: ReviewCreate,
    response: Response,
    customer: Customer | None = Depends(optional_customer),
    customer_contact: str | None = Query(default=None, max_length=60),
    db: Session = Depends(get_db),
) -> ReviewResponse:
    try:
        review, created = review_service.write_review(
            db,
            venue_public_id=body.venue_public_id,
            rating=body.rating,
            comment=body.comment,
            customer=customer,
            # A signed-in customer carries their own contact, so the caller does
            # not have to supply it — and cannot supply someone else's.
            customer_contact=customer_contact
            or (customer.phone or customer.email if customer else ""),
        )
    except ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    # A re-submit replaces the earlier rating rather than adding a second one,
    # so answer 200 rather than implying a new row appeared.
    if not created:
        response.status_code = 200
    return _to_response(review, mine=True)


@router.get("", summary="A venue's reviews (newest first, paged)")
def list_reviews(
    venue_public_id: UUID,
    page: Page = Depends(),
    response: Response = None,
    customer: Customer | None = Depends(optional_customer),
    db: Session = Depends(get_db),
) -> list[ReviewResponse]:
    try:
        venue, rows = review_service.list_reviews(
            db, venue_public_id, limit=page.limit, offset=page.offset
        )
    except ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    set_total(response, review_service.count_reviews(db, venue.id))
    return [
        _to_response(row, mine=customer is not None and row.customer_id == customer.id)
        for row in rows
    ]


@router.get("/summary", summary="Average rating and star breakdown")
def rating_summary(
    venue_public_id: UUID, db: Session = Depends(get_db)
) -> VenueRatingResponse:
    try:
        venue, average, count, distribution = review_service.rating_summary(
            db, venue_public_id
        )
    except ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return VenueRatingResponse(
        venue_public_id=venue.public_id,
        average=average,
        count=count,
        distribution=distribution,
    )
