"""venue closures (holidays)

Revision ID: a7c1f2b8d934
Revises: e6b3a0c5f7d2
Create Date: 2026-10-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c1f2b8d934"
down_revision: str | None = "e6b3a0c5f7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venue_closures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("venue_id", sa.Integer(), sa.ForeignKey("venues.id"), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("public_id", name="uq_venue_closures_public_id"),
    )
    op.create_index(
        "ix_venue_closures_venue_dates", "venue_closures", ["venue_id", "starts_on", "ends_on"]
    )


def downgrade() -> None:
    op.drop_index("ix_venue_closures_venue_dates", table_name="venue_closures")
    op.drop_table("venue_closures")
