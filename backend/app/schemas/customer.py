from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _email(value: str) -> str:
    """Lower-cased login address, checked without a third-party validator.

    The rule is the one the backend can actually enforce: one `@`, with a
    non-empty local part and a dot-bearing domain. Anything stricter rejects
    addresses that do work, and the real test is whether mail arrives.
    """
    value = value.strip().lower()
    if value.count("@") != 1 or value.startswith("@") or value.endswith("@"):
        raise ValueError("That does not look like an email address.")
    domain = value.split("@", 1)[1]
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("That does not look like an email address.")
    return value


class CustomerRegister(BaseModel):
    """Creating an account. The email is the login; `phone` is where the club
    reaches them, which is usually a WhatsApp number rather than that email."""

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(default="", max_length=60)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _email(value)

    @field_validator("display_name", "phone")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class CustomerLogin(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _email(value)


class CustomerResponse(BaseModel):
    """What a client may see about an account — never the password hash."""

    public_id: UUID
    email: str
    display_name: str
    phone: str
    is_active: bool

    model_config = {"from_attributes": True}


class CustomerSessionResponse(BaseModel):
    """Sign-in/register answer. The token also rides in `X-Customer-Token`
    so a client that only reads headers still gets it."""

    token: str
    token_type: str = "customer"
    customer: CustomerResponse
