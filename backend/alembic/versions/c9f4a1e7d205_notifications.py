"""guest notifications (outbox)

Revision ID: c9f4a1e7d205
Revises: a7c1f2b8d934
Create Date: 2026-10-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9f4a1e7d205"
down_revision: str | None = "a7c1f2b8d934"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("group_public_id", sa.Uuid(), nullable=True),
        sa.Column("event", sa.String(length=24), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("recipient", sa.String(length=160), nullable=False),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("transport", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("error", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("public_id", name="uq_notifications_public_id"),
    )
    op.create_index("ix_notifications_status_id", "notifications", ["status", "id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_status_id", table_name="notifications")
    op.drop_table("notifications")
