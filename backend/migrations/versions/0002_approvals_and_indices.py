"""approval events + pending-approvals index + query indices

Versions the approval_events table (previously created only by the local create_all path), adds
the pending_approvals read-model, and the indices the queue and retention queries rely on.

Revision ID: 0002_approvals
Revises: 0001_initial
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_approvals"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_events",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column("thread_id", sa.String(), nullable=False, index=True),
        sa.Column("actor_key", sa.String(), nullable=False, index=True),
        sa.Column("decision", sa.String(), nullable=False, index=True),
        sa.Column("created_at", sa.String(), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "pending_approvals",
        sa.Column("thread_id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_audit_records_created_at", "audit_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_records_created_at", table_name="audit_records")
    op.drop_table("pending_approvals")
    op.drop_table("approval_events")
