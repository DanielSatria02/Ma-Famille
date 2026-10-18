"""add booking group id

Revision ID: c7d2e9a1f4b3
Revises: b41f7c9de205
Create Date: 2026-10-18

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7d2e9a1f4b3"
down_revision: str | None = "b41f7c9de205"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("group_public_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_bookings_group_public_id", "bookings", ["group_public_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_group_public_id", table_name="bookings")
    op.drop_column("bookings", "group_public_id")
