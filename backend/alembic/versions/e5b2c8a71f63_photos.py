"""photos on venues and courts: bytes in, a stable URL out

Revision ID: e5b2c8a71f63
Revises: d31a7c95be42
Create Date: 2026-10-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5b2c8a71f63"
down_revision: str | None = "d31a7c95be42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("venues", sa.Column("image_url", sa.String(length=300), nullable=True))
    op.add_column("courts", sa.Column("image_url", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("courts", "image_url")
    op.drop_column("venues", "image_url")
