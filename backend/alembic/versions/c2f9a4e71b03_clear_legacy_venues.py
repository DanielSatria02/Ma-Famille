"""clear the legacy demo rows and hold the sport to padel

Revision ID: c2f9a4e71b03
Revises: b8e2f1a04c73
Create Date: 2026-10-20

The app used to book futsal and badminton courts; it books padel courts now.
The database still held the old rows, and the API answers a listing of courts
with a 500 as soon as one of them is a sport the response schema does not
know — one row left over from a demo seed takes the whole court list down.

So the leftovers go. The two branches of Ma-Famille Premiere stay; everything
else — the forty-four clubs the seed used to collect, the demo venue, and the
futsal and badminton courts under them — is removed, children first, because
the foreign keys do not cascade.

The branches keep one court each, which is what the seed holds now. The
extra courts are from the older, larger seed, and a demo branch with five
courts is not the demo anybody was asked for. Their slots, bookings, payments
and notifications go with them.

The sport is then pinned in the database as well as in the code: a CHECK
constraint says a court is a padel court. A row that the API cannot answer for
is a row that should not exist, and the database is the last place that can
say so before the API does.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2f9a4e71b03"
down_revision: str | None = "b8e2f1a04c73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The branches the chain runs, and the court each of them keeps.
BRANCHES = {
    "Pondok Indah": "Lapangan Padel 1",
    "Lebak Bulus": "Lapangan Padel 1",
}


def _kept_ids() -> str:
    """The ids of the two branches, as a literal list for the SQL below.

    Written out rather than bound: the ids are integers that came out of the
    database itself, and a literal list keeps the statements readable when
    they are copied into a psql session to see what a deploy would do.
    """
    rows = op.get_bind().execute(
        sa.text("SELECT id FROM venues WHERE name IN ('Pondok Indah', 'Lebak Bulus')")
    )
    ids = [int(row[0]) for row in rows]
    return ", ".join(str(i) for i in ids) if ids else "NULL"


def upgrade() -> None:
    bind = op.get_bind()
    kept = _kept_ids()

    # Payments and notifications point at bookings, bookings at slots, slots
    # at courts, courts at a club. The order is the reverse of the way down.
    for statement in (
        """
        DELETE FROM payments
        WHERE booking_id IN (
            SELECT b.id FROM bookings b
            JOIN slots s ON s.id = b.slot_id
            JOIN courts c ON c.id = s.court_id
            WHERE c.venue_id NOT IN (%s)
        )
        """,
        """
        DELETE FROM notifications
        WHERE booking_id IN (
            SELECT b.id FROM bookings b
            JOIN slots s ON s.id = b.slot_id
            JOIN courts c ON c.id = s.court_id
            WHERE c.venue_id NOT IN (%s)
        )
        """,
        """
        DELETE FROM bookings
        WHERE slot_id IN (
            SELECT s.id FROM slots s
            JOIN courts c ON c.id = s.court_id
            WHERE c.venue_id NOT IN (%s)
        )
        """,
        """
        DELETE FROM slots
        WHERE court_id IN (
            SELECT c.id FROM courts c
            WHERE c.venue_id NOT IN (%s)
        )
        """,
        """
        DELETE FROM reviews
        WHERE venue_id NOT IN (%s)
        """,
        """
        DELETE FROM promotions
        WHERE venue_id IS NOT NULL AND venue_id NOT IN (%s)
        """,
        """
        DELETE FROM venue_closures
        WHERE venue_id NOT IN (%s)
        """,
        """
        DELETE FROM venue_hours
        WHERE venue_id NOT IN (%s)
        """,
        """
        DELETE FROM courts
        WHERE venue_id NOT IN (%s)
        """,
        """
        DELETE FROM venues
        WHERE id NOT IN (%s)
        """,
    ):
        bind.execute(sa.text(statement % kept))

    # The branches keep one court each. The extra ones came from the older,
    # larger seed; their hours go with them.
    #
    # A court is identified by its name inside a branch, so a second court
    # with the same name is the same court twice over — the oldest one stays
    # and the copy goes, because a manager looking at "Lapangan Padel 1" and
    # finding two of them has no way to tell them apart.
    for branch, court_name in BRANCHES.items():
        # The court that stays is the oldest one with that name in that
        # branch. COALESCE(-1) is the case where the branch has no such court:
        # nothing equals -1, so every court of the branch is on the way out,
        # which is what should happen to a branch whose court was renamed.
        doomed = f"""
            SELECT c.id FROM courts c
            JOIN venues v ON v.id = c.venue_id
            WHERE v.name = '{branch}'
              AND c.id <> COALESCE((
                  SELECT MIN(c2.id) FROM courts c2
                  WHERE c2.venue_id = v.id AND c2.name = '{court_name}'
              ), -1)
        """
        for statement in (
            f"""
            DELETE FROM payments
            WHERE booking_id IN (
                SELECT b.id FROM bookings b
                JOIN slots s ON s.id = b.slot_id
                WHERE s.court_id IN ({doomed})
            )
            """,
            f"""
            DELETE FROM notifications
            WHERE booking_id IN (
                SELECT b.id FROM bookings b
                JOIN slots s ON s.id = b.slot_id
                WHERE s.court_id IN ({doomed})
            )
            """,
            f"""
            DELETE FROM bookings
            WHERE slot_id IN (
                SELECT s.id FROM slots s WHERE s.court_id IN ({doomed})
            )
            """,
            f"""
            DELETE FROM slots
            WHERE court_id IN ({doomed})
            """,
            f"""
            DELETE FROM courts
            WHERE id IN ({doomed})
            """,
        ):
            bind.execute(sa.text(statement))

    # A court left over under a branch that survives still has to become
    # padel, or the constraint below would refuse the insert.
    bind.execute(
        sa.text("UPDATE courts SET sport = 'padel' WHERE sport IS DISTINCT FROM 'padel'")
    )

    op.create_check_constraint(
        "ck_courts_sport", "courts", "sport = 'padel'"
    )


def downgrade() -> None:
    op.drop_constraint("ck_courts_sport", "courts", type_="check")
