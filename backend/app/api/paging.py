"""Shared paging for list endpoints.

Pages are slices of the same JSON array the clients already parse — the total
travels in an `X-Total-Count` header (exposed through CORS) so nothing has to
change shape just to load the next page.
"""

from fastapi import Query, Response

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


class Page:
    def __init__(
        self,
        limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
        offset: int = Query(0, ge=0),
    ):
        self.limit = limit
        self.offset = offset


def set_total(response: Response, total: int) -> None:
    response.headers["X-Total-Count"] = str(total)
