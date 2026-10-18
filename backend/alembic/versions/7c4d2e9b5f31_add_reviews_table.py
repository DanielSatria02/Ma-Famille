"""add reviews table

Revision ID: 7c4d2e9b5f31
Revises: 5b9e3c7f8a21
Create Date: 2026-10-18

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c4d2e9b5f31"
down_revision: str | None = "5b9e3c7f8a21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
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
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("customer_contact", sa.String(length=60), nullable=False),
        sa.Column("booking_group_public_id", sa.String(length=36), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.UniqueConstraint("customer_id", "venue_id", name="uq_reviews_customer_venue"),
    )
    op.create_index("ix_reviews_venue_id", "reviews", ["venue_id"])
    op.create_index("ix_reviews_customer_id", "reviews", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_reviews_customer_id", table_name="reviews")
    op.drop_index("ix_reviews_venue_id", table_name="reviews")
    op.drop_table("reviews")
