"""SQLAlchemy-backed implementations of the audit repository and the verdict ledger."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    ApprovalEventRow,
    AuditRecordRow,
    PendingApprovalRow,
    PrecedentRow,
    VerdictClaimRow,
)
from app.domain import ApprovalDecision, ApprovalEvent, AuditRecord
from app.ports.memory import MemoryPort, PrecedentRecord
from app.ports.repository import ApprovalLedger, AuditRepository, VerdictLedger

# How many same-subject candidates the precedent query pulls before ranking by tag overlap; the
# scan stays bounded regardless of how much history accumulates.
_PRECEDENT_CANDIDATES = 50


class SqlAuditRepository(AuditRepository):
    """Append-only audit log over SQLAlchemy. The full record is stored as a JSON payload."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def append(self, record: AuditRecord) -> None:
        with self._session_factory() as session:
            session.add(
                AuditRecordRow(
                    audit_id=record.audit_id,
                    change_id=record.change_id,
                    thread_id=record.thread_id,
                    created_at=record.created_at,
                    payload=record.model_dump(mode="json"),
                )
            )
            session.commit()

    def get(self, audit_id: str) -> AuditRecord | None:
        with self._session_factory() as session:
            row = session.get(AuditRecordRow, audit_id)
            return AuditRecord.model_validate(row.payload) if row is not None else None

    def latest_for_change(self, change_id: str) -> AuditRecord | None:
        with self._session_factory() as session:
            stmt = (
                select(AuditRecordRow)
                .where(AuditRecordRow.change_id == change_id)
                .order_by(AuditRecordRow.created_at.desc())
                .limit(1)
            )
            row = session.execute(stmt).scalars().first()
            return AuditRecord.model_validate(row.payload) if row is not None else None

    def thread_ids_completed_before(self, cutoff: str) -> list[str]:
        # ISO-8601 UTC strings compare lexicographically, so the index on created_at applies.
        with self._session_factory() as session:
            stmt = (
                select(AuditRecordRow.thread_id)
                .group_by(AuditRecordRow.thread_id)
                .having(func.max(AuditRecordRow.created_at) < cutoff)
            )
            return list(session.execute(stmt).scalars().all())


class SqlVerdictLedger(VerdictLedger):
    """Exactly-once verdict ledger. A duplicate claim hits the composite PK and is rejected."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def try_claim(self, thread_id: str, idempotency_key: str) -> bool:
        with self._session_factory() as session:
            session.add(VerdictClaimRow(thread_id=thread_id, idempotency_key=idempotency_key))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return False
            return True

    def mark_completed(self, thread_id: str, idempotency_key: str, audit_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(VerdictClaimRow, (thread_id, idempotency_key))
            if row is not None:
                row.audit_id = audit_id
                session.commit()

    def result_for(self, thread_id: str, idempotency_key: str) -> str | None:
        with self._session_factory() as session:
            row = session.get(VerdictClaimRow, (thread_id, idempotency_key))
            return row.audit_id if row is not None else None

    def purge_thread(self, thread_id: str) -> None:
        with self._session_factory() as session:
            session.execute(delete(VerdictClaimRow).where(VerdictClaimRow.thread_id == thread_id))
            session.commit()


class SqlApprovalLedger(ApprovalLedger):
    """Append-only approval-event log over SQLAlchemy. The full event is stored as JSON."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def append(self, event: ApprovalEvent) -> None:
        with self._session_factory() as session:
            session.add(
                ApprovalEventRow(
                    event_id=event.event_id,
                    thread_id=event.thread_id,
                    actor_key=event.actor.key(),
                    decision=event.decision.value,
                    created_at=event.at,
                    payload=event.model_dump(mode="json"),
                )
            )
            session.commit()

    def list_for_thread(self, thread_id: str) -> list[ApprovalEvent]:
        with self._session_factory() as session:
            stmt = (
                select(ApprovalEventRow)
                .where(ApprovalEventRow.thread_id == thread_id)
                .order_by(ApprovalEventRow.created_at)
            )
            rows = session.execute(stmt).scalars().all()
            return [ApprovalEvent.model_validate(r.payload) for r in rows]

    def thread_ids(self) -> list[str]:
        with self._session_factory() as session:
            stmt = select(ApprovalEventRow.thread_id).distinct()
            return list(session.execute(stmt).scalars().all())

    def first_note(self, thread_id: str, decision: ApprovalDecision) -> str:
        with self._session_factory() as session:
            stmt = (
                select(ApprovalEventRow.payload)
                .where(
                    ApprovalEventRow.thread_id == thread_id,
                    ApprovalEventRow.decision == decision.value,
                )
                .order_by(ApprovalEventRow.created_at)
                .limit(1)
            )
            payload = session.execute(stmt).scalars().first()
            return str(payload.get("note", "")) if isinstance(payload, dict) else ""

    def mark_pending(self, thread_id: str, at: str) -> None:
        with self._session_factory() as session:
            if session.get(PendingApprovalRow, thread_id) is None:
                session.add(PendingApprovalRow(thread_id=thread_id, created_at=at))
                try:
                    session.commit()
                except IntegrityError:  # concurrent mark: the row already exists, which is fine
                    session.rollback()

    def clear_pending(self, thread_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(PendingApprovalRow, thread_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def pending_thread_ids(self) -> list[str]:
        with self._session_factory() as session:
            stmt = select(PendingApprovalRow.thread_id).order_by(PendingApprovalRow.created_at)
            return list(session.execute(stmt).scalars().all())


class SqlPrecedentStore(MemoryPort):
    """Same-database precedent memory with explainable retrieval (subject + tag overlap)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, record: PrecedentRecord) -> None:
        with self._session_factory() as session:
            if session.get(PrecedentRow, record.thread_id) is not None:
                return  # one precedent per trial; re-runs are no-ops
            session.add(
                PrecedentRow(
                    thread_id=record.thread_id,
                    subject=record.subject,
                    created_at=record.created_at,
                    payload=record.model_dump(mode="json"),
                )
            )
            session.commit()

    def find_similar(
        self, subject: str, tags: list[str], *, top_k: int = 3
    ) -> list[PrecedentRecord]:
        with self._session_factory() as session:
            stmt = (
                select(PrecedentRow.payload)
                .where(PrecedentRow.subject == subject)
                .order_by(PrecedentRow.created_at.desc())
                .limit(_PRECEDENT_CANDIDATES)
            )
            payloads = session.execute(stmt).scalars().all()
        records = [PrecedentRecord.model_validate(p) for p in payloads]
        wanted = set(tags)
        # Rank by shared tags (the explainable signal), most recent first within a rank.
        records.sort(key=lambda r: len(wanted & set(r.tags)), reverse=True)
        return records[:top_k]
