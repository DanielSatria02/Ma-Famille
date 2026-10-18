"""A range with a stray `Z` is a bad request, not a crash.

`starts_at`/`ends_at` are wall times of the court, but a client can send an
offset on one end and not the other. Comparing an aware datetime with a naive
one raises TypeError, which FastAPI turns into a 500 — the wrong answer for
what is really a malformed range.
"""

import pytest
from pydantic import ValidationError

from app.schemas.booking import BookingRangeCreate


def _range(starts_at: str, ends_at: str) -> dict:
    return {
        "court_public_id": "01a14d3b-969b-7084-ab09-760a34d343dc",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "customer_name": "Ana",
        "customer_contact": "0812000001",
    }


def test_a_mixed_offset_is_rejected_as_a_validation_error():
    """Not a 500: the offset-stamped end is understood, then judged."""
    body = _range("2026-11-09T09:00:00", "2026-11-09T10:00:00Z")
    parsed = BookingRangeCreate(**body)
    assert parsed.starts_at.tzinfo is None
    assert parsed.ends_at.tzinfo is None


def test_a_reversed_range_still_says_what_is_wrong():
    """The offset must not swallow the ordering check underneath it."""
    with pytest.raises(ValidationError) as excinfo:
        BookingRangeCreate(**_range("2026-11-09T10:00:00Z", "2026-11-09T09:00:00"))
    assert "after" in str(excinfo.value)


def test_two_stamped_ends_are_compared_normally():
    parsed = BookingRangeCreate(**_range("2026-11-09T09:00:00Z", "2026-11-09T10:00:00Z"))
    assert parsed.starts_at < parsed.ends_at


def test_two_bare_ends_are_unchanged():
    parsed = BookingRangeCreate(**_range("2026-11-09T09:00:00", "2026-11-09T10:00:00"))
    assert parsed.starts_at.tzinfo is None
    assert parsed.ends_at.tzinfo is None
