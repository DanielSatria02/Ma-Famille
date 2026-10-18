"""venues: tags and coordinates

Revision ID: e6b3a0c5f7d2
Revises: d9e4b7c2a1f8
Create Date: 2026-10-18

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e6b3a0c5f7d2"
down_revision: str | None = "d9e4b7c2a1f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "venues",
        sa.Column(
            "tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
    )
    op.add_column("venues", sa.Column("lat", sa.Float(), nullable=True))
    op.add_column("venues", sa.Column("lng", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("venues", "lng")
    op.drop_column("venues", "lat")
    op.drop_column("venues", "tags")
