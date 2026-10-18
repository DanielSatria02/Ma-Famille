from pydantic import BaseModel, Field


class ClientConfig(BaseModel):
    """Settings a client has to know to behave correctly.

    Public and read-only: no secrets, only what the UI cannot guess — how long a
    pending booking lives, whether logging in as manager can work at all, and
    whether the payment gateway is wired up.

    `payment_configured` answers "can a checkout be opened right now", not "are
    both key fields filled in". A SNAP API key fills the field and signs nothing
    this gateway accepts, so a client told "yes" would show a pay button that
    fails. `payment_problem` carries the reason, for whoever is looking at a
    deploy rather than a visitor.
    """

    booking_ttl_minutes: int = Field(ge=1)
    booking_min_lead_days: int = Field(ge=0)
    manager_login_enabled: bool
    payment_configured: bool
    payment_problem: str = ""
