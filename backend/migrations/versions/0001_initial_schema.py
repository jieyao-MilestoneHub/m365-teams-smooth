"""initial schema: audit_records and verdict_claims

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_records",
        sa.Column("audit_id", sa.String(), primary_key=True),
        sa.Column("change_id", sa.String(), nullable=False, index=True),
        sa.Column("thread_id", sa.String(), nullable=False, index=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "verdict_claims",
        sa.Column("thread_id", sa.String(), primary_key=True),
        sa.Column("idempotency_key", sa.String(), primary_key=True),
        sa.Column("audit_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("verdict_claims")
    op.drop_table("audit_records")
