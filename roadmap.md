# Roadmap

Milestones are decomposed into small, single-responsibility pull requests. Each PR is meant to be
reviewable in about 30 minutes and to carry one concern — one adapter, one node, one router. Order
is roughly sequential; PRs within a milestone can often proceed in parallel.

Status legend: ☐ todo · ◐ in progress · ☑ done.

## M0 — Scaffold

- ☐ `chore: backend skeleton` — `backend/` package layout, `pyproject.toml` (ruff/mypy/pytest),
  `app/main.py` app factory, `app/config.py` settings.
- ☐ `feat: health endpoint` — `GET /api/health` + a smoke test.
- ☐ `chore: frontend skeleton` — `frontend/` Next.js app, lint/build config.
- ☐ `chore: dev tooling` — `Makefile`, `.env.example`, `docker-compose.yml`, repo `docs/` stubs.

## M1 — Domain & ports

- ☐ `feat: domain models` — `domain/models.py`, `domain/enums.py`, `domain/errors.py` (pure, no SDKs).
- ☐ `feat: integration port` — `ports/integration.py` (`IntegrationAdapter`, `Capability`).
- ☐ `feat: persistence ports` — `ports/repository.py`, `ports/checkpointer.py`.
- ☐ `feat: llm & notifier ports` — `ports/llm.py`, `ports/notifier.py`.

## M2 — LangGraph single-agent

- ☐ `feat: graph state` — `agent/state.py` state schema.
- ☐ `feat: plan node` — `agent/nodes/plan_node.py` (LLM → plan validated against capabilities).
- ☐ `feat: policy node` — `agent/nodes/policy_node.py` (deterministic risk → requires_approval).
- ☐ `feat: execute node` — `agent/nodes/execute_node.py` (adapter calls, dry-run aware).
- ☐ `feat: audit node` — `agent/nodes/audit_node.py` (append-only before/after + rollback hints).
- ☐ `feat: graph wiring + approval interrupt` — `agent/graph.py`, `agent/routing.py`,
  `agent/runner.py` (durable interrupt + resume).

## M3 — Integration adapters

- ☐ `feat: adapter base + registry` — `adapters/integrations/base.py`, `registry.py` (real-vs-mock
  by config, `FORCE_ALL_MOCK`).
- ☐ `feat: GitHub adapter (real)` — issues + milestone operations, recorded tests.
- ☐ `feat: mock Outlook adapter` — with fixtures.
- ☐ `feat: mock Planner adapter` — with fixtures.
- ☐ `feat: mock Graph adapter` — with fixtures.
- ☐ `feat: mock CRM adapter` — with fixtures.
- ☐ `feat: mock ServiceNow adapter` — with fixtures.
- ☐ `feat: mock SharePoint adapter` — with fixtures.
- ☐ `feat: mock Entra adapter` — with fixtures.

## M4 — Persistence

- ☐ `feat: db + migrations` — `adapters/persistence/db.py`, `orm.py`, initial Alembic migration.
- ☐ `feat: plan & audit repositories` — `plan_repo.py`, `audit_repo.py`.
- ☐ `feat: LangGraph checkpointer` — SQLite saver behind the `CheckpointStore` port.

## M5 — REST API (dashboard contract)

- ☐ `feat: services layer` — `services/decision_service.py`, `services/approval_service.py`.
- ☐ `feat: decisions & plans routers` — `POST /api/decisions`, `GET /api/decisions/{id}`,
  `GET .../plan`.
- ☐ `feat: approvals router` — `POST /api/decisions/{id}/approval` (idempotent resume).
- ☐ `feat: audit & integrations routers` — `GET /api/audit`, `GET /api/audit/{id}`,
  `GET /api/integrations`.
- ☐ `feat: status stream` — optional SSE `GET /api/decisions/{id}/stream`.

## M6 — MCP server

- ☐ `feat: MCP server mount` — `mcp/server.py` mounted on the FastAPI app.
- ☐ `feat: MCP tools` — `submit_decision`, `get_plan`, `approve_plan`, `get_status` (thin → services).
- ☐ `feat: MCP resources` — plan / audit / capabilities.
- ☐ `feat: OAuth2 resource server` — `mcp/auth.py`, shared `security/oauth.py`, local dev issuer.

## M7 — Dashboard

- ☐ `feat: audit log view` — list + detail (before/after, rollback hints).
- ☐ `feat: plan review & approval UI` — render plan + risk, approve/reject.
- ☐ `feat: integration status badges` — real-vs-mock indicators from `/api/integrations`.

## M8 — Microsoft 365 entry (pending tenant)

- ☐ `feat: declarative agent manifest` — `m365/declarative-agent.json`.
- ☐ `feat: MCP plugin manifest` — `m365/plugin-manifest.json` pointing at the MCP server.
- ☐ `feat: approval Adaptive Card` — `m365/adaptive-cards/approval-card.json`.

## Backlog — extensibility

- ☐ Connected/multi-agent: executor sub-agents behind a `SubAgentRegistry`.
- ☐ Policy-as-data: editable risk rules.
- ☐ Additional integrations and Adaptive Cards.
- ☐ Further scenarios beyond Launch Change: Customer Escalation, Access Governance.
- ☐ Background execution + retries for long-running steps.
- ☐ Postgres + Entra ID auth for non-local deployment.

## ADRs to record along the way

- Durable interrupt vs. MCP/HTTP statelessness for the approval gap.
- `IntegrationAdapter` port as the integration boundary.
- SQLite-now / Postgres-later, swappable persistence.
