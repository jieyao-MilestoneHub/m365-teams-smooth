"""precedent memory: compact summaries of finished trials for retrieval

Revision ID: 0003_precedents
Revises: 0002_approvals
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_precedents"
down_revision: str | None = "0002_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "precedents",
        sa.Column("thread_id", sa.String(), primary_key=True),
        sa.Column("subject", sa.String(), nullable=False, index=True),
        sa.Column("created_at", sa.String(), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("precedents")
