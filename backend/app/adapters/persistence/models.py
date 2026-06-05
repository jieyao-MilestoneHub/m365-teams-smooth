"""SQLAlchemy ORM rows.

Audit records store the full domain object as a JSON payload (with a few columns for querying);
the audit log is append-only. The verdict ledger enforces exactly-once verdicts via its composite
primary key ``(thread_id, idempotency_key)``.
"""

from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM rows."""


class AuditRecordRow(Base):
    """One append-only audit record. ``payload`` is the serialized domain AuditRecord."""

    __tablename__ = "audit_records"

    audit_id: Mapped[str] = mapped_column(String, primary_key=True)
    change_id: Mapped[str] = mapped_column(String, index=True)
    thread_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class VerdictClaimRow(Base):
    """A claimed verdict. The composite PK makes a second claim of the same key a conflict."""

    __tablename__ = "verdict_claims"

    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String, primary_key=True)
    audit_id: Mapped[str | None] = mapped_column(String, nullable=True)


class ApprovalEventRow(Base):
    """One append-only approval action (send/withdraw/approve/reject). ``payload`` is the event."""

    __tablename__ = "approval_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String, index=True)
    actor_key: Mapped[str] = mapped_column(String, index=True)
    decision: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class PrecedentRow(Base):
    """One past ruling's compact summary, retrieved as precedent for future trials."""

    __tablename__ = "precedents"

    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    subject: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class ConversationReferenceRow(Base):
    """Where a user can be reached for proactive bot messages.

    ``payload`` is the serialized Bot Framework conversation reference, recorded whenever the user
    installs or talks to the bot. One row per identity key — a user is addressable by Entra object
    id and by lowercased UPN, so both keys point at the same reference. A disposable read-model:
    the next turn rewrites it.
    """

    __tablename__ = "conversation_references"

    identity_key: Mapped[str] = mapped_column(String, primary_key=True)
    oid: Mapped[str] = mapped_column(String)
    upn: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class PendingApprovalRow(Base):
    """Index of trials currently awaiting an approver, so the queue never scans history.

    Maintained by the service at the transitions: inserted when a trial is sent for approval,
    deleted when the quorum resolves or the requester withdraws. The append-only event log stays
    the source of truth; this row is a disposable read-model.
    """

    __tablename__ = "pending_approvals"

    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[str] = mapped_column(String)
