# ADR-0003: SQLite now, Postgres later, behind a swappable checkpoint saver

- **Status:** Accepted
- **Date:** 2026-06-02

## Context

Both application persistence (plans, audit records, verdict ledger) and the LangGraph checkpoint
store need a database. Local development must run with zero setup (a file is enough), while a later
deployment will want a managed database. Neither the graph nor the services should depend on a
concrete database or saver implementation.

## Decision

Drive persistence by `DB_URL` (SQLite locally, Postgres later) via SQLAlchemy + Alembic. Wrap the
LangGraph saver behind a `CheckpointStore` port; the SQLite implementation wraps LangGraph's
SQLite saver and is the only place the saver type appears. Audit records are append-only.

## Consequences

- Swapping SQLite → Postgres is a configuration change plus one adapter, no graph/service edits.
- The checkpoint store and the application database can evolve independently.
- Append-only audit means corrections are new records, never updates.
