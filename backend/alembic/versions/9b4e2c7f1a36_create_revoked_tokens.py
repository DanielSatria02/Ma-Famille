"""create revoked_tokens table

Revision ID: 9b4e2c7f1a36
Revises: 3c9d1a7e5f82
Create Date: 2026-10-18

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9b4e2c7f1a36"
down_revision: str | None = "3c9d1a7e5f82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_revoked_tokens_public_id", "revoked_tokens", ["public_id"], unique=True
    )
    op.create_index(
        "ix_revoked_tokens_token_hash", "revoked_tokens", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_revoked_tokens_token_hash", table_name="revoked_tokens")
    op.drop_index("ix_revoked_tokens_public_id", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")
