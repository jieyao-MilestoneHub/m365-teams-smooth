# Architecture — the standing engineering contract

The system turns a team decision into a reviewable, approvable, auditable cross-system execution.
Keep the layering and SOLID boundaries below intact; they are what make the project extensible and
demo-able at once.

## Shape

```
Microsoft 365 Copilot Chat / Teams
  └─ Declarative Agent (manifest in m365/)        ← required M365 entry
        │ MCP + OAuth2
        ▼
  FastAPI process (backend/)
     ├─ mcp/        MCP server: tools + resources + OAuth2 resource server
     ├─ api/        REST routers for the Next.js dashboard
     ├─ services/   single business layer (REST + MCP both delegate here — no duplication)
     ├─ agent/      LangGraph single-agent: plan → policy → [approval interrupt] → execute → audit
     ├─ ports/      abstract interfaces (DIP boundary)
     ├─ adapters/   integrations (real GitHub + mock others), persistence, llm, notifiers
     └─ domain/     pure models/enums/errors (no framework or SDK imports)
  Next.js (frontend/) = audit + approval dashboard
  SQLite (local) → Postgres (later), DB_URL-driven
```

## Non-negotiable boundaries

- **Dependency Inversion:** `agent/` and `services/` depend on `ports/` only — never on the GitHub
  SDK, SQLAlchemy, or an LLM client directly. Concrete implementations live in `adapters/`.
- **One business layer:** REST routers and MCP tools are thin façades over `services/`. No business
  logic in routers or tools.
- **Pure domain:** `domain/` imports nothing from FastAPI, LangGraph, or any adapter.

## LangGraph single-agent

- **State** (serializable, checkpointed): `thread_id, decision_id, raw_decision, source, run_mode,
  plan, risk, approval, results, audit_id, errors`.
- **Nodes** (single responsibility each):
  - `plan` — LLM extracts an `ExecutionPlan`; every step validated against **registered adapter
    capabilities** (no hallucinated actions).
  - `policy` — deterministic risk scoring → `requires_approval`. Rules are data, not code.
  - `execute` — registry → adapter per step; honors `run_mode` (DRY_RUN returns predicted effects,
    no side effects).
  - `audit` — append-only before/after snapshot + rollback hints.
- **Approval = durable interrupt:** suspend at `interrupt()` / `interrupt_before=["execute"]`,
  checkpointed by `thread_id`. The submitting request returns immediately; a later approval call
  rehydrates from the checkpointer and resumes. **Never hold the graph in memory across the approval
  gap.**
- **Dry-run** is a first-class state field, not a separate code path.

## SOLID integration adapters

- Port `IntegrationAdapter`: `capabilities() / validate() / execute(step, mode) / fetch_before() /
  suggest_rollback()`.
- `BaseIntegrationAdapter` template-methods the dry-run branch and error→`IntegrationError` mapping.
- `IntegrationRegistry` selects **real vs mock per system from config** (`integration_mode`, plus a
  `FORCE_ALL_MOCK` flag to run with zero external credentials).
- **Open/Closed:** a new integration = one adapter module + one registration. No edits to graph,
  services, REST, or MCP.

## Persistence

- SQLAlchemy + Alembic, `DB_URL`-driven (SQLite local, Postgres later).
- Audit records are **append-only** — never updated. Rollback hints are advisory data, not
  auto-executed.
- LangGraph checkpoints behind a `CheckpointStore` port so the saver is swappable.

## Extensibility seams (do not paint over)

- **Connected/multi-agent:** nodes are state-in/state-out; an executor sub-agent per system slots in
  behind a `SubAgentRegistry` mirroring `IntegrationRegistry`.
- **More MCP tools / Adaptive Cards:** `mcp/tools.py` is a thin façade; card templates are data in
  `m365/adaptive-cards/`.
- **Notifier port** for future approval channels (email, webhook) without graph changes.

Record significant choices as ADRs under `docs/adr/` (e.g. the interrupt-vs-MCP-statelessness
decision).
