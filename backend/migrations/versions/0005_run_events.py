"""run events: append-only per-node and per-step pipeline progress log

Revision ID: 0005_run_events
Revises: 0004_conversation_refs
Create Date: 2026-06-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_run_events"
down_revision: str | None = "0004_conversation_refs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("thread_id", "seq", name="uq_run_events_thread_seq"),
    )
    op.create_index("ix_run_events_thread_id", "run_events", ["thread_id"])
    op.create_index("ix_run_events_thread_seq", "run_events", ["thread_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_run_events_thread_seq", table_name="run_events")
    op.drop_index("ix_run_events_thread_id", table_name="run_events")
    op.drop_table("run_events")
