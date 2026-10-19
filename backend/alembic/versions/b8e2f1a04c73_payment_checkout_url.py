"""keep the DOKU checkout page with the payment

Revision ID: b8e2f1a04c73
Revises: 4a8f2e6c1b93
Create Date: 2026-10-19

The hosted checkout URL was handed back to the caller and then forgotten, which
meant a customer who closed the payment page had no way back to it: the page
asked DOKU for a new checkout, DOKU issued a new invoice, and the booking ended
up with two invoices for one visit. Storing the link with the payment is what
lets the payment page offer the same checkout again after a refresh.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8e2f1a04c73"
down_revision: str | None = "4a8f2e6c1b93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    ("checkout_url", sa.String(length=500)),
    ("provider_token_id", sa.String(length=80)),
)


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.add_column("payments", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("payments", name)
