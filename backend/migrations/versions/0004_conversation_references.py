"""conversation references: where users are reachable for proactive bot messages

Revision ID: 0004_conversation_refs
Revises: 0003_precedents
Create Date: 2026-06-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_conversation_refs"
down_revision: str | None = "0003_precedents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_references",
        sa.Column("identity_key", sa.String(), primary_key=True),
        sa.Column("oid", sa.String(), nullable=False),
        sa.Column("upn", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("conversation_references")
