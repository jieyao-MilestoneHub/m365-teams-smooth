# ADR-0001: Durable verdict interrupt over an in-memory approval gap

- **Status:** Accepted
- **Date:** 2026-06-02

## Context

The court must pause between proposing a plan and executing it, to collect a human **verdict**.
That gap can last minutes or days, and the approval may arrive over a different surface (REST or
MCP) and a different process than the one that submitted the change. Holding the running graph in
memory across this gap would not survive a restart, would not scale, and would couple submit and
resume to one process.

## Decision

Model the verdict as a **durable interrupt**. The LangGraph court compiles with
`interrupt_before=["execute"]` and a checkpointer keyed by `thread_id`. `submit_change` runs
`intake → … → policy+quorum`, then suspends and persists a checkpoint, returning immediately.
A later `cast_verdict` rehydrates from the checkpoint and resumes into `execute → audit`. The graph
is **never held in memory across the gap**. Idempotency is enforced in the service layer (a verdict
ledger) so casting the same verdict twice — over REST or MCP — is a no-op.

## Consequences

- Submit and resume can run in different processes; the state of record is the checkpoint.
- All LangGraph invoke/resume calls are confined to one runner module, isolating version risk.
- Requires a checkpoint store (see [ADR-0003](./0003-swappable-checkpoint-saver.md)) and a verdict
  ledger with a uniqueness constraint per `(thread_id, idempotency_key)`.
