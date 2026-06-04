# ADR-0009: Agentic roles under governed autonomy

- **Status:** Accepted
- **Date:** 2026-06-04

## Context

Until now the LLM appeared in exactly one place — intake parsing — while evidence gathering and
plan generation were hardcoded per subject. That made the system a reliable workflow, not an
agent: perception could not explore, generation could not reason, nothing was remembered across
trials, and execution was never checked against intent. The goal was to make the courtroom roles
genuinely agentic without surrendering any of the governance guarantees (deterministic policy,
durable approval gates, reproducible offline trials, the cost bounds of ADR-0008).

## Decision

**The agent's freedom lives in perception and generation; the safety verdict stays deterministic.**

1. **Prosecutor — agentic perception.** `LlmEvidenceGatherer` wraps each subject's deterministic
   gatherer: the deterministic core always runs first (its evidence and the policy tags stay
   reproducible — tags never come from the LLM), then the LLM selects up to `MAX_AGENTIC_READS`
   additional reads from the registry's read catalog and contributes a bounded assessment. Every
   selected read is validated against the catalog and its params schema before execution — the
   intake hallucination guard now covers tool selection.
2. **Defender — agentic generation with binding refusal.** `LlmPlanner` drafts the execution plan
   from the write catalog, but the deterministic baseline's plan *kind* is binding: a refusal
   (safe alternative) can be enriched, never reversed. One invalid step rejects the whole drafted
   plan — a partial plan could execute a different change than the one reviewed.
3. **Memory — precedents in the court's own database.** Every finished trial is recorded as a
   compact precedent (best-effort, never blocking the audit); the agentic prompts cite the top-3
   retrieved by *explainable* similarity — same subject, ranked by shared policy tags, then
   recency, over a bounded candidate scan. Same-database storage adds no external service or
   attack surface and keeps data residency identical to the audit log; a semantic-search store can
   replace it behind `MemoryPort`.
4. **Reflection — deterministic effect verification.** A `verify` node compares each live step's
   requested params to the adapter-reported after-state; mismatches are recorded into the trial
   record and flagged on the result card. Advisory only, like rollback hints.
5. **What stays deterministic, on purpose:** risk scoring, quorum derivation, verdict options,
   approval enforcement, and refusal authority. Governance must be reproducible and auditable;
   that is the substance of governed autonomy, not a limitation of it.

### Engagement and bounds

- Agentic paths engage when a real LLM is configured (the same switch as the parser); offline and
  `FORCE_ALL_MOCK` runs stay fully deterministic, so tests and demos are unchanged.
- Per-trial LLM ceiling: **3 calls** (intake, gatherer, planner), each with `max_tokens` and a
  timeout; agentic reads ≤ `MAX_AGENTIC_READS`; precedent citations ≤ 3 × 200 chars; every LLM
  component falls back to its deterministic counterpart on any failure.

### Sub-agent registry: deemed redundant

The reserved "SubAgentRegistry" seam was evaluated and **not** built. The nodes are already
state-in/state-out callables injected at the composition root — that *is* the sub-agent seam. A
role→node registry would add an indirection layer with no behavioral gain; the roles became real
agents by giving them reasoning (this ADR), not by registering them. If a role is ever
externalized (e.g. a remote reviewer service), it implements the same node callable and the
container swaps it — no registry required.

## Consequences

- The same codebase is a deterministic workflow offline and a reasoning agent in deployment, with
  one switch and no behavioral drift in the governance layer.
- Hallucination cannot reach execution: unknown capabilities are rejected at selection time,
  unknown tags are inert to rule packs, and invalid plans fall back whole.
- Trade-offs accepted: the agentic paths are exercised in tests only via scripted LLMs (real-model
  behavior is validated in deployment); the deterministic-first design spends a few extra reads
  per trial compared to a pure-LLM pipeline — that redundancy is the price of reproducible
  governance.
