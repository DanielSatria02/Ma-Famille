"""give reviews the timestamp defaults the model already promises

Revision ID: 4a8f2e6c1b93
Revises: 7c4d2e9b5f31
Create Date: 2026-10-18

The reviews table was created without the `server_default` its model declares,
so every insert failed the not-null constraint on created_at. Tests never saw
it: SQLite's `create_all` builds the table from the model, which does have the
default, so only the migrated database did.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4a8f2e6c1b93"
down_revision: str | None = "7c4d2e9b5f31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The default has to be SQL the database evaluates per row, not a value
    # read once now — `server_default` takes DDL text.
    op.alter_column(
        "reviews",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "reviews",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "reviews",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "reviews",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )