"""courts: facility kind and unset rates

Revision ID: d9e4b7c2a1f8
Revises: c7d2e9a1f4b3
Create Date: 2026-10-18

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9e4b7c2a1f8"
down_revision: str | None = "c7d2e9a1f4b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "courts",
        sa.Column(
            "kind", sa.String(length=20), nullable=False, server_default="court"
        ),
    )
    op.alter_column("courts", "price_weekday", existing_type=sa.Integer(), nullable=True)
    op.alter_column("courts", "price_weekend", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Unpriced rows cannot survive the NOT NULL rollback: price them at 0.
    op.execute("UPDATE courts SET price_weekday = 0 WHERE price_weekday IS NULL")
    op.execute("UPDATE courts SET price_weekend = 0 WHERE price_weekend IS NULL")
    op.alter_column(
        "courts", "price_weekday", existing_type=sa.Integer(), nullable=False
    )
    op.alter_column(
        "courts", "price_weekend", existing_type=sa.Integer(), nullable=False
    )
    op.drop_column("courts", "kind")
