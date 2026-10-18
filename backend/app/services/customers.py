"""Customer accounts: register, sign in, and prove who a request belongs to.

A customer used to be nothing but a contact string typed into the booking
form, so "My bookings" trusted whatever number was entered and the same
person with a typo owned a different history. These functions turn that into
a real identity: a password checked with PBKDF2, and an opaque session token
whose hash is the only thing stored.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.passwords import hash_password, verify_password
from app.models.customer import Customer
from app.models.customer_session import CustomerSession

# Sessions are stateless-ish: the row is the source of truth for "is this
# still signed in", so its lifetime is a setting, not a constant.
SESSION_HOURS = 24 * 14
_TOKEN_BYTES = 32


class CustomerError(Exception):
    """A register/sign-in refusal whose message is safe to show the client."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register(
    db: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    phone: str = "",
) -> Customer:
    """Creates the account or raises CustomerError with a usable reason."""
    email = normalize_email(email)
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise CustomerError("That does not look like an email address.")
    if len(password) < 8:
        raise CustomerError("Use a password of at least 8 characters.")
    if not display_name.strip():
        raise CustomerError("Tell us the name to put on bookings.")

    if db.scalars(select(Customer).where(Customer.email == email)).first():
        # Same message as a wrong password on purpose: telling an attacker
        # which addresses are registered is what makes credential stuffing work.
        raise CustomerError("That email is already registered.")

    customer = Customer(
        email=email,
        display_name=display_name.strip()[:120],
        phone=phone.strip()[:60],
        password_hash=hash_password(password),
    )
    db.add(customer)
    # Flushed, not committed: the caller mints the session next, and both
    # writes belong in one transaction. Committing here would leave an account
    # that exists but cannot be signed in to if that second step fails.
    db.flush()
    db.refresh(customer)
    return customer


def authenticate(db: Session, *, email: str, password: str) -> Customer:
    email = normalize_email(email)
    customer = db.scalars(select(Customer).where(Customer.email == email)).first()
    # Always run the hash, even when the account is missing: returning early
    # would let the response time reveal which emails exist.
    stored = customer.password_hash if customer else hash_password("not-a-real-password")
    ok = verify_password(password, stored)
    if customer is None or not ok or not customer.is_active:
        raise CustomerError("Wrong email or password.")
    return customer


def start_session(db: Session, customer: Customer) -> str:
    """Mints a session and returns the token — the only time it is visible."""
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    session = CustomerSession(
        customer_id=customer.id,
        token_hash=token_hash(token),
        expires_at=datetime.now(UTC) + timedelta(hours=SESSION_HOURS),
    )
    db.add(session)
    db.commit()
    return token


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def customer_for_token(db: Session, token: str | None) -> Customer | None:
    """The signed-in customer, or None when the token is absent/expired."""
    if not token:
        return None
    session = db.scalars(
        select(CustomerSession).where(CustomerSession.token_hash == token_hash(token))
    ).first()
    if session is None:
        return None
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    customer = db.get(Customer, session.customer_id)
    if customer is None or not customer.is_active:
        return None
    session.last_seen_at = datetime.now(UTC)
    db.commit()
    return customer


def end_session(db: Session, token: str | None) -> bool:
    """Drops the session row behind a token. True when one was found."""
    if not token:
        return False
    session = db.scalars(
        select(CustomerSession).where(CustomerSession.token_hash == token_hash(token))
    ).first()
    if session is None:
        return False
    db.delete(session)
    db.commit()
    return True
