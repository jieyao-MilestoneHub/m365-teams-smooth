# Command Center — Decision-to-Action Agent

Turn a team decision into a reviewable, approvable, auditable set of actions across the tools your
team already uses.

Decisions get made in chat and meetings — "slip the launch one week", "escalate this customer",
"grant the contractor two weeks of access" — and then nobody updates the issue tracker, the
calendar, the ticketing system, or the permissions. Command Center reads the decision, proposes a
cross-system **execution plan**, asks a human to approve it, executes it through real APIs, and
keeps an **audit trail** with rollback suggestions.

It is not a chatbot. It is an action layer: **plan → approve → execute → audit.**

## How it works

1. **Plan** — the agent reads the decision and produces a structured execution plan: which systems
   change, what actions run, and the predicted effect of each step.
2. **Policy** — each plan is risk-scored. Low-risk plans can run directly; anything sensitive
   requires human approval.
3. **Approve** — the plan is presented for review (as an Adaptive Card in chat, or in the
   dashboard). A human approves, edits, or rejects.
4. **Execute** — approved steps run through pluggable integration adapters.
5. **Audit** — every step records a before/after snapshot and a rollback hint, append-only.

A **dry-run** mode shows exactly what *would* change without touching any external system.

## Architecture

```
Microsoft 365 Copilot Chat / Teams
  └─ Declarative Agent (m365/)              the chat entry point
        │  MCP + OAuth 2.0
        ▼
  FastAPI service (backend/)
     ├─ MCP server      tools + resources the chat agent calls (OAuth2-secured)
     ├─ REST API        consumed by the dashboard
     ├─ Services        single business layer shared by MCP and REST
     ├─ Agent           LangGraph: plan → policy → [approval] → execute → audit
     ├─ Ports           abstract interfaces (the dependency-inversion boundary)
     └─ Adapters        GitHub (real) + Outlook/Planner/CRM/ServiceNow/SharePoint/Entra (mock)
  Next.js (frontend/)  audit + approval dashboard
  SQLite (local) → Postgres (later)
```

Design highlights:

- **LangGraph single-agent** orchestration keeps the flow controllable and inspectable; the approval
  step is a **durable interrupt** — the run suspends to a checkpoint and resumes when approved, so
  nothing is held in memory across the wait.
- **Ports & adapters (SOLID).** Integrations sit behind one `IntegrationAdapter` interface. GitHub
  is a real adapter; the rest are mock adapters returning realistic data. Real-vs-mock is chosen by
  configuration, so the whole system runs locally with no external credentials.
- **One business layer.** The MCP tools (for the chat agent) and the REST API (for the dashboard)
  both delegate to the same services — no duplicated logic.

The first end-to-end scenario implemented is **Launch Change Commander**: a launch-date change that
updates a GitHub milestone/issue and (via mock adapters) the calendar, planner, and announcements.

## Tech stack

- **Frontend:** Next.js (TypeScript)
- **Backend:** FastAPI (Python 3.11+)
- **Agent orchestration:** LangGraph
- **Integration protocol:** Model Context Protocol (MCP) with OAuth 2.0
- **Persistence:** SQLAlchemy + Alembic over SQLite (Postgres-ready)

## Repository layout

```
backend/    FastAPI app: agent/, mcp/, api/, services/, ports/, adapters/, domain/
frontend/   Next.js dashboard
m365/        declarative agent manifest, plugin manifest, Adaptive Card templates
docs/        architecture, ADRs, API contract, integration guide
scripts/     developer/demo scripts (e.g. verify.sh, seed data)
```

## Getting started (local)

> The project runs fully locally. No Microsoft 365 tenant is required for development; the chat
> entry point is wired separately once a tenant is available.

```bash
# Backend
cd backend
uv sync                 # or: poetry install
cp ../.env.example ../.env
uvicorn app.main:app --reload

# Frontend
cd ../frontend
pnpm install
pnpm dev
```

Then open the dashboard (default http://localhost:3000) and the API health check
(http://localhost:8000/api/health).

## Configuration

Set via environment variables (see `.env.example`):

- `DB_URL` — defaults to a local SQLite file.
- `INTEGRATION_MODE` — per-system `real` or `mock` selection (default: GitHub `real`, others `mock`).
- `FORCE_ALL_MOCK=true` — run every integration as a mock, with zero external credentials.
- `DRY_RUN_DEFAULT` — whether new decisions default to dry-run.
- `GITHUB_TOKEN` — required only when the GitHub adapter runs in `real` mode.
- `OAUTH_*` — MCP OAuth2 settings; a local dev issuer is used when no tenant is configured.

**Never commit secrets.** Use environment variables or a secret store.

## Status

This project is under active development. See [`roadmap.md`](./roadmap.md) for milestones and
[`verify.md`](./verify.md) for the end-to-end verification checklist.
