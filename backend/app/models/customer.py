from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, PublicIdMixin, TimestampMixin


class Customer(Base, PKMixin, PublicIdMixin, TimestampMixin):
    """Someone who books with an account instead of a bare contact string.

    Before this existed a customer was only their WhatsApp number or email,
    typed into the form each time: the same person with a typo owned a
    different history, and "My bookings" could show someone else's visits to
    anyone who guessed the number. An account turns that into a signed-in
    identity the booking can be attached to.

    Email is the login and is unique case-insensitively (stored lower-case).
    """

    __tablename__ = "customers"

    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # The contact they want venues to reach them on. Kept separate from email
    # because it is usually a WhatsApp number, not the login address.
    phone: Mapped[str] = mapped_column(
        String(60), nullable=False, default="", server_default=text("''")
    )
    # PBKDF2 string from app.core.passwords — never a bare password.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
