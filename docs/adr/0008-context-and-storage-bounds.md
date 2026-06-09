# ADR-0008: Context and storage bounds (resource-explosion posture)

- **Status:** Accepted
- **Date:** 2026-06-04

## Context

An architecture review examined the agent against the failure modes long-running LLM systems hit:
unbounded context growth, checkpoint/state sprawl, query costs that scale with history instead of
with open work, and storage that only ever grows. The single-graph design was already sound — one
deterministic pipeline, exactly one LLM call per trial (intake parsing) with a deterministic
fallback, structured output validated against registered capabilities, a durable idempotent
interrupt, bounded retries, and fixed-cardinality metrics. The review found five gaps, all fixed;
this ADR records the resulting posture so future changes preserve it.

## Decision

1. **Queries scale with open work, never with history.** The pending-approvals queue reads a
   dedicated `pending_approvals` read-model maintained at the workflow transitions (insert on
   send, delete on terminal decide/withdraw). The append-only event log stays the source of
   truth; the index is disposable. Any future "list things in state X" surface must follow this
   pattern rather than scanning all threads.
2. **Working storage has a retention window; the audit log is permanent.** A finished trial's
   LangGraph checkpoints and verdict-claim rows are purged once its latest audit record is older
   than `RETENTION_DAYS` (default 30) via `python -m scripts.purge` (idempotent; candidates are
   the live-checkpoint ∩ finished set, so a cleared backlog re-checks for free). Audit records
   are never deleted — they are the system of record.
3. **Inputs are bounded at the edge and rejected, not truncated.** A change request is a sentence
   or two in chat; `MAX_REQUEST_CHARS` (default 1000) and a non-blank check guard `submit_change`,
   surfacing as the typed `invalid_request` (422 / JSON-RPC invalid params) on both REST and MCP.
   The court only ever deliberates on exactly what was asked.
4. **Every outbound dependency is bounded and degradable.** The LLM call carries `max_tokens`
   (default 1024) plus its existing timeout, and parse failures fall back to the deterministic
   parser; knowledge grounding is capped (3 facts × 600 chars) and a provider failure becomes an
   evidence-level error, not a failed trial. A prompt-size regression test pins that the prompt
   scales with the bounded input.
5. **State that is serialized per checkpoint stays bounded.** The accumulating `errors` list is
   capped (50 entries + truncation marker). The audit payload stores each fact once: before/after
   snapshots and rollback hints are views derived from `trial.results`, not duplicated fields.

## Consequences

- Steady-state cost is proportional to *open* trials: queue reads, checkpoint storage (within the
  retention window), and per-trial LLM spend are all capped by configuration.
- Operators get one knob per bound (`RETENTION_DAYS`, `MAX_REQUEST_CHARS`, `LLM_MAX_TOKENS`) and
  one scheduled command (`scripts.purge`); defaults are safe with no scheduling at small scale.
- The Postgres path inherits the same shape: the new indices (`approval_events.decision`,
  `created_at`, `audit_records.created_at`) and the read-model pattern carry over; the LangGraph
  checkpoint tables remain saver-owned and swap with the `CheckpointStore` adapter.
- Trade-offs accepted: a purged trial can no longer be resumed or time-travel-debugged (its audit
  record remains the full account); oversized requests fail loudly instead of being helpfully
  trimmed; the error-list cap can hide repeats past 50 (the marker says how many were dropped).
