"""add peak-hour pricing columns to courts

Revision ID: 5d8f3a2b7c91
Revises: 9b4e2c7f1a36
Create Date: 2026-10-18

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5d8f3a2b7c91"
down_revision: str | None = "9b4e2c7f1a36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("courts", sa.Column("price_peak", sa.Integer(), nullable=True))
    op.add_column("courts", sa.Column("peak_start_hour", sa.Integer(), nullable=True))
    op.add_column("courts", sa.Column("peak_end_hour", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("courts", "peak_end_hour")
    op.drop_column("courts", "peak_start_hour")
    op.drop_column("courts", "price_peak")
