"""add customer_id to bookings

Revision ID: 5b9e3c7f8a21
Revises: 8f2c1d4a9b60
Create Date: 2026-10-18

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5b9e3c7f8a21"
down_revision: str | None = "8f2c1d4a9b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable on purpose: a booking made without signing in has no account to
    # point at, and the contact string still carries it.
    op.add_column(
        "bookings",
        sa.Column("customer_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bookings_customer_id", "bookings", "customers", ["customer_id"], ["id"]
    )
    op.create_index(
        op.f("ix_bookings_customer_id"), "bookings", ["customer_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_bookings_customer_id"), table_name="bookings")
    op.drop_constraint("fk_bookings_customer_id", "bookings", type_="foreignkey")
    op.drop_column("bookings", "customer_id")
