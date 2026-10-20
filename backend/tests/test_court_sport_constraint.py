"""A court is a padel court, in the database as well as in the schema.

The app used to book futsal and badminton. The API stopped accepting those
sports, but the database still held rows from the older seed, and a listing
that touched one of them came back a 500 — one leftover row took the whole
court list down, and the dashboard with it.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.court import Court
from app.models.venue import Venue


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _venue(db):
    venue = Venue(name="Pondok Indah", address="Jakarta")
    db.add(venue)
    db.flush()
    return venue


def test_a_court_can_be_padel():
    db = _session()
    venue = _venue(db)
    db.add(
        Court(
            venue_id=venue.id,
            name="Lapangan Padel 1",
            sport="padel",
            price_weekday=90000,
            price_weekend=120000,
        )
    )
    db.commit()
    assert db.query(Court).count() == 1


def test_a_court_cannot_be_another_sport():
    db = _session()
    venue = _venue(db)
    db.add(
        Court(
            venue_id=venue.id,
            name="Lapangan Futsal Utama",
            sport="futsal",
            price_weekday=60000,
            price_weekend=80000,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_the_constraint_is_named_so_a_failure_points_at_it():
    names = {constraint.name for constraint in Court.__table__.constraints}
    assert "ck_courts_sport" in names
