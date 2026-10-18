from pydantic import BaseModel, Field, model_validator

# "HH:MM" so clients can render and compare without parsing ISO timestamps.
ClockTime = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class VenueHoursUpdate(BaseModel):
    opens_at: str = ClockTime
    closes_at: str = ClockTime
    is_closed: bool = False

    @model_validator(mode="after")
    def _closes_after_opens(self):
        if not self.is_closed and self.closes_at <= self.opens_at:
            raise ValueError("closes_at must be after opens_at")
        return self


class VenueHoursResponse(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    day: str
    opens_at: str
    closes_at: str
    is_closed: bool
    # True while the day still runs on the settings default (no stored row).
    is_default: bool = False
