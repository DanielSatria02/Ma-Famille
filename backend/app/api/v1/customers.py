"""Customer register / sign-in / who-am-I.

The session token travels in `X-Customer-Token`. Booking routes read it too,
so a signed-in customer does not have to retype their contact to prove a
booking is theirs.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.customer import (
    CustomerLogin,
    CustomerRegister,
    CustomerResponse,
    CustomerSessionResponse,
)
from app.services import audit as audit_service
from app.services import customers as customer_service

router = APIRouter(prefix="/customers", tags=["customers"])


def _token_from_header(x_customer_token: str | None) -> str | None:
    return x_customer_token.strip() or None if x_customer_token else None


def current_customer(
    db: Session = Depends(get_db),
    x_customer_token: str | None = Header(default=None, alias="X-Customer-Token"),
):
    """The signed-in customer, or a 401 with a message worth showing."""
    customer = customer_service.customer_for_token(db, _token_from_header(x_customer_token))
    if customer is None:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    return customer


@router.post(
    "/register",
    status_code=201,
    summary="Create a customer account (public)",
    response_model=CustomerSessionResponse,
    responses={409: {"description": "That email is already registered"}},
)
def register(body: CustomerRegister, response: Response, db: Session = Depends(get_db)):
    try:
        customer = customer_service.register(
            db,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            phone=body.phone or "",
        )
    except customer_service.CustomerError as exc:
        # A duplicate email answers 409 so the form can offer "sign in" instead
        # of retrying; the other refusals are the caller's input, so 422.
        status = 409 if "already registered" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    token = customer_service.start_session(db, customer)
    # An account is an identity, so it enters the same change log every other
    # write does.
    audit_service.record(
        db,
        actor=customer.email,
        action="customer.register",
        entity_type="customer",
        entity_public_id=customer.public_id,
    )
    response.headers["X-Customer-Token"] = token
    return CustomerSessionResponse(
        token=token,
        customer=CustomerResponse.model_validate(customer, from_attributes=True),
    )


@router.post("/login", summary="Sign in (public)", response_model=CustomerSessionResponse)
def login(body: CustomerLogin, response: Response, db: Session = Depends(get_db)):
    try:
        customer = customer_service.authenticate(db, email=body.email, password=body.password)
    except customer_service.CustomerError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    token = customer_service.start_session(db, customer)
    response.headers["X-Customer-Token"] = token
    return CustomerSessionResponse(
        token=token,
        customer=CustomerResponse.model_validate(customer, from_attributes=True),
    )


@router.post("/logout", summary="End the current session", status_code=204)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    x_customer_token: str | None = Header(default=None, alias="X-Customer-Token"),
):
    customer_service.end_session(db, _token_from_header(x_customer_token))
    # 204 either way: being already signed out is the state the caller wanted.
    response.status_code = 204
    return None


@router.get("/me", summary="The signed-in customer", response_model=CustomerResponse)
def me(customer=Depends(current_customer)):
    return customer
