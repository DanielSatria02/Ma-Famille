"""create promotions table, add discount columns to bookings

Revision ID: 7e4b9d2a6f13
Revises: 5d8f3a2b7c91
Create Date: 2026-10-18

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7e4b9d2a6f13"
down_revision: str | None = "5d8f3a2b7c91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promotions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_promotions_public_id", "promotions", ["public_id"], unique=True)
    op.create_index("ix_promotions_code", "promotions", ["code"], unique=True)

    # A booking carries the discount that was taken off it. For a multi-hour
    # group the whole discount sits on the group's first row, so summing the
    # rows' discounts gives the group's discount exactly once.
    op.add_column(
        "bookings", sa.Column("discount", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("bookings", sa.Column("promo_code", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "promo_code")
    op.drop_column("bookings", "discount")
    op.drop_index("ix_promotions_code", table_name="promotions")
    op.drop_index("ix_promotions_public_id", table_name="promotions")
    op.drop_table("promotions")
