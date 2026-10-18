"""create customer_sessions table

Revision ID: 8f2c1d4a9b60
Revises: 61e0eb9d7733
Create Date: 2026-10-18

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8f2c1d4a9b60"
down_revision: str | None = "61e0eb9d7733"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Hand-written: autogenerate also proposes dropping indexes on unrelated
    # tables (naming noise), which would break the app if applied.
    op.create_table(
        "customer_sessions",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
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
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_customer_sessions_customer_id"),
        "customer_sessions",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_sessions_token_hash"),
        "customer_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_customer_sessions_public_id"),
        "customer_sessions",
        ["public_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_customer_sessions_public_id"), table_name="customer_sessions")
    op.drop_index(op.f("ix_customer_sessions_token_hash"), table_name="customer_sessions")
    op.drop_index(op.f("ix_customer_sessions_customer_id"), table_name="customer_sessions")
    op.drop_table("customer_sessions")
