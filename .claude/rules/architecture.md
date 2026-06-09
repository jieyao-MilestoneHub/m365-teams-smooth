# Architecture — the standing engineering contract

The system turns a risky team decision into a reviewable, approvable, auditable cross-system
execution — and, when the decision is unsafe, refuses it and proposes a safer alternative. Keep the
layering and SOLID boundaries below intact; they are what make the project extensible and demo-able
at once.

## Shape

```
Microsoft 365 Copilot Chat / Teams
  └─ Declarative Agent (manifest in m365/)        ← required M365 entry
        │ MCP + OAuth2
        ▼
  FastAPI process (backend/)
     ├─ mcp/        MCP server: tools + resources + OAuth2 resource server (primary surface)
     ├─ api/        minimal REST: health + the read-only run page (signed links; no business logic)
     ├─ services/   single business layer (REST + MCP both delegate here — no duplication)
     ├─ agent/      LangGraph court: intake → impact → options → policy+quorum → [verdict] → execute → audit
     ├─ ports/      abstract interfaces (DIP boundary)
     ├─ adapters/   integrations (real GitHub + mock others), persistence, llm, notifiers
     └─ domain/     pure models/enums/errors (no framework or SDK imports)
  Teams Adaptive Card = the decision UI (Change Court card). The one web surface is the
  read-only pipeline run page (/runs/{thread_id}, HMAC-signed deep links — ADR-0011):
  it inspects a trial's run, never decides. No dashboard beyond it.
  SQLite (local) → Postgres (later), DB_URL-driven
```

## Non-negotiable boundaries

- **Dependency Inversion:** `agent/` and `services/` depend on `ports/` only — never on the GitHub
  SDK, SQLAlchemy, or an LLM client directly. Concrete implementations live in `adapters/`.
- **One business layer:** MCP tools and REST routers are thin façades over `services/`. No business
  logic in routers or tools. The Adaptive Card renders data the services produce.
- **Pure domain:** `domain/` imports nothing from FastAPI, LangGraph, or any adapter.

## LangGraph single-agent "Change Court"

A single, inspectable graph, presented as courtroom roles (Prosecutor = impact, Defender = options,
Clerk = audit, Executor = execute). It is one agent today; the multi-agent path is a seam, not a
rewrite (see below).

- **State** (serializable, checkpointed): `thread_id, change_id, raw_request, source, run_mode,
  change, impact, options, plan, risk, quorum, verdict, results, audit_id, errors`.
- **Nodes** (single responsibility each):
  - `intake` — parse the request into a structured `Change`; **validate every requested action
    against registered adapter capabilities** (hallucination guard — unsupported actions are blocked,
    not planned).
  - `impact` (Prosecutor) — gather second-order consequences via adapter **read** capabilities
    (blockers, customer commitments, renewal value, schedule conflicts) → `ImpactEvidence`.
  - `options` (Defender) — produce a feasible `ExecutionPlan`; when the request is unsafe, produce a
    **safe alternative** (e.g. private preview instead of GA; least-privilege + expiry instead of
    broad access).
  - `policy + quorum` — deterministic risk scoring → `requires_approval`; derive the **required
    approvers** (quorum) from impact tags and the available **verdict options**. Rules are data, not code.
  - `execute` (Executor) — registry → adapter per step; honors `run_mode` (DRY_RUN returns predicted
    effects, no side effects).
  - `audit` (Clerk) — append-only before/after snapshot + rollback hints + the full trial record
    (impact, options, approvers, verdict).
- **Verdict = durable interrupt:** suspend at `interrupt()` / `interrupt_before=["execute"]`,
  checkpointed by `thread_id`. The submitting request returns immediately; a later `cast_verdict`
  call rehydrates from the checkpointer and resumes. **Never hold the graph in memory across the
  verdict gap.** Casting the same verdict twice is idempotent — no double execution.
- **Dry-run** is a first-class state field, not a separate code path.

## SOLID integration adapters

- Port `IntegrationAdapter`: `capabilities() / validate() / read(query) / execute(step, mode) /
  fetch_before() / suggest_rollback()`. Capabilities are typed and split into **read** (evidence for
  the impact node) and **write** (actions for execution).
- `BaseIntegrationAdapter` template-methods the dry-run branch and error→`IntegrationError` mapping.
- `IntegrationRegistry` selects **real vs mock per system from config** (`integration_mode`, plus a
  `FORCE_ALL_MOCK` flag to run with zero external credentials).
- **Open/Closed:** a new integration = one adapter module + one registration. No edits to graph,
  services, REST, or MCP.
- **Scope discipline:** only the adapters the headline demo (Informed Approval) and the additional
  capabilities the engine already handles require are built — GitHub (real) and mock Outlook,
  Planner, SharePoint, Teams, CRM, Entra. Others (ServiceNow, a generic Graph adapter) are backlog.

## Persistence

- SQLAlchemy + Alembic, `DB_URL`-driven (SQLite local, Postgres later).
- Audit records are **append-only** — never updated. Rollback hints are advisory data, not
  auto-executed.
- LangGraph checkpoints behind a `CheckpointStore` port so the saver is swappable.

## Extensibility seams (do not paint over)

- **Connected/multi-agent:** nodes are state-in/state-out; the courtroom roles (Prosecutor, Defender,
  Clerk, Executor) slot in behind a `SubAgentRegistry` mirroring `IntegrationRegistry`.
- **More MCP tools / Adaptive Cards:** `mcp/tools.py` is a thin façade; card templates are data in
  `m365/adaptive-cards/`.
- **Notifier port** for future approval channels (email, webhook) without graph changes.

Record significant choices as ADRs under `docs/adr/` (e.g. the verdict-interrupt-vs-MCP-statelessness
decision).
