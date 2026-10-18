"""payment lifecycle: provider answer, failure reason, refund stamp

Revision ID: d31a7c95be42
Revises: c9f4a1e7d205
Create Date: 2026-10-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d31a7c95be42"
down_revision: str | None = "c9f4a1e7d205"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    ("provider_request_id", sa.String(length=64)),
    ("provider_status", sa.String(length=40)),
    ("failure_reason", sa.String(length=160)),
    ("refunded_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.add_column("payments", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("payments", name)
