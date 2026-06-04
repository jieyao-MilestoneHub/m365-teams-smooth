"""SQLAlchemy-backed implementations of the audit repository and the verdict ledger."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import ApprovalEventRow, AuditRecordRow, VerdictClaimRow
from app.domain import ApprovalEvent, AuditRecord
from app.ports.repository import ApprovalLedger, AuditRepository, VerdictLedger


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
