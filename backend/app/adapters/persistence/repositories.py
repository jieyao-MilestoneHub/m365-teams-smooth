"""SQLAlchemy-backed implementations of the audit repository and the verdict ledger."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    ApprovalEventRow,
    AuditRecordRow,
    ConversationReferenceRow,
    PendingApprovalRow,
    PrecedentRow,
    RunEventRow,
    VerdictClaimRow,
)
from app.domain import ApprovalDecision, ApprovalEvent, AuditRecord
from app.domain.run_events import RunEvent, RunEventKind
from app.ports.conversation_store import ConversationStore
from app.ports.memory import MemoryPort, PrecedentRecord
from app.ports.repository import ApprovalLedger, AuditRepository, VerdictLedger
from app.ports.run_event_sink import RunEventReader, RunEventSink

logger = logging.getLogger(__name__)

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


class SqlRunEventSink(RunEventSink, RunEventReader):
    """Append-only run-event log over SQLAlchemy.

    Each ``emit`` opens its own short-lived session and commits immediately, so an event is
    visible to a concurrent run-view poll while the graph is still executing. Emission is
    best-effort: any failure is logged and swallowed — observability must never fail a change.
    """

    # One retry absorbs the only realistic seq race (a parallel emit for the same thread); the
    # unique constraint turns anything beyond that into a loud failure instead of a reorder.
    _SEQ_RETRIES = 2

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def emit(
        self,
        thread_id: str,
        kind: RunEventKind,
        name: str,
        *,
        status: str = "",
        payload: dict[str, object] | None = None,
    ) -> None:
        if not thread_id:
            return  # nodes exercised outside a trial (unit tests, ad-hoc runs) have no run log
        try:
            for _ in range(self._SEQ_RETRIES):
                if self._try_insert(thread_id, kind, name, status, payload or {}):
                    return
        except Exception:
            logger.warning("run_event.emit_failed", extra={"node": name}, exc_info=True)

    def _try_insert(
        self,
        thread_id: str,
        kind: RunEventKind,
        name: str,
        status: str,
        payload: dict[str, object],
    ) -> bool:
        with self._session_factory() as session:
            next_seq = session.execute(
                select(func.coalesce(func.max(RunEventRow.seq), 0)).where(
                    RunEventRow.thread_id == thread_id
                )
            ).scalar_one() + 1
            session.add(
                RunEventRow(
                    thread_id=thread_id,
                    seq=next_seq,
                    kind=kind.value,
                    name=name,
                    status=status,
                    created_at=datetime.now(UTC).isoformat(),
                    payload=payload,
                )
            )
            try:
                session.commit()
            except IntegrityError:  # lost the seq race; retry with a fresh MAX
                session.rollback()
                return False
            return True

    def list_after(self, thread_id: str, after_seq: int = 0) -> list[RunEvent]:
        with self._session_factory() as session:
            stmt = (
                select(RunEventRow)
                .where(RunEventRow.thread_id == thread_id, RunEventRow.seq > after_seq)
                .order_by(RunEventRow.seq)
            )
            rows = session.execute(stmt).scalars().all()
            return [
                RunEvent(
                    thread_id=r.thread_id,
                    seq=r.seq,
                    kind=RunEventKind(r.kind),
                    name=r.name,
                    status=r.status,
                    payload=dict(r.payload),
                    created_at=r.created_at,
                )
                for r in rows
            ]


class SqlConversationStore(ConversationStore):
    """Conversation references over SQLAlchemy: one upserted row per identity key."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(self, *, oid: str, upn: str, reference: dict[str, object]) -> None:
        keys = {k for k in (oid.strip(), upn.strip().lower()) if k}
        if not keys:
            return
        now = datetime.now(UTC).isoformat()
        with self._session_factory() as session:
            for key in keys:
                row = session.get(ConversationReferenceRow, key)
                if row is None:
                    session.add(
                        ConversationReferenceRow(
                            identity_key=key, oid=oid, upn=upn, updated_at=now, payload=reference
                        )
                    )
                else:
                    row.oid, row.upn, row.updated_at, row.payload = oid, upn, now, reference
            try:
                session.commit()
            except IntegrityError:  # concurrent turn already wrote the row; the next one rewrites
                session.rollback()

    def get(self, identity: str) -> dict[str, object] | None:
        key = identity.strip()
        if not key:
            return None
        with self._session_factory() as session:
            row = session.get(ConversationReferenceRow, key) or session.get(
                ConversationReferenceRow, key.lower()
            )
            return dict(row.payload) if row is not None else None


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
        if not subject:
            # An empty subject means "never extracted", not a retrieval pattern — citing every
            # subjectless trial as precedent would be noise, not case law.
            return []
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
