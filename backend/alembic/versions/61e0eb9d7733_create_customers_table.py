"""create customers table

Revision ID: 61e0eb9d7733
Revises: 7e4b9d2a6f13
Create Date: 2026-10-18 18:36:22.069710

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "61e0eb9d7733"
down_revision: str | None = "7e4b9d2a6f13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Written by hand: autogenerate also proposed dropping indexes on every
    # other table, which is naming-convention noise rather than a real change
    # — applying it would have broken the app.
    timestamps = [
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
    ]
    op.create_table(
        "customers",
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column(
            "phone",
            sa.String(length=60),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        *timestamps,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_customers_email"), "customers", ["email"], unique=True
    )
    op.create_index(
        op.f("ix_customers_public_id"), "customers", ["public_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_customers_public_id"), table_name="customers")
    op.drop_index(op.f("ix_customers_email"), table_name="customers")
    op.drop_table("customers")
