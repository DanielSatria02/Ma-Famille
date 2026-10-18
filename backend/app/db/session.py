from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def session_for_request(request=None) -> Session:
    """A session outside the request dependency: audit rows, WebSocket frames.

    A `get_db` override (tests, any future per-request database) has to be
    honoured, or work that opens its own session reads a different database
    than the request that triggered it — and finds nothing there. The override
    is a dependency that yields, so it is advanced to its first value.
    """
    override = None
    if request is not None:
        override = getattr(request.app, "dependency_overrides", {}).get(get_db)
    if override is not None:
        produced = override()
        return produced if isinstance(produced, Session) else next(produced)
    return SessionLocal()
