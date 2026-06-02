"""The database schema initializes and the ORM rows round-trip."""

from __future__ import annotations

from sqlalchemy import select

from app.adapters.persistence.db import init_db, make_engine, make_session_factory
from app.adapters.persistence.models import AuditRecordRow, VerdictClaimRow


def test_init_db_creates_tables_and_rows_persist() -> None:
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    factory = make_session_factory(engine)

    with factory() as session:
        session.add(
            AuditRecordRow(
                audit_id="a1",
                change_id="c1",
                thread_id="t1",
                created_at="2026-06-02T00:00:00Z",
                payload={"status": "done"},
            )
        )
        session.add(VerdictClaimRow(thread_id="t1", idempotency_key="k1", audit_id=None))
        session.commit()

    with factory() as session:
        row = session.get(AuditRecordRow, "a1")
        assert row is not None and row.payload["status"] == "done"
        claims = session.execute(select(VerdictClaimRow)).scalars().all()
        assert len(claims) == 1
