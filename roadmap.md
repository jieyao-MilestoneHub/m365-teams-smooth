# Roadmap

This roadmap describes the path from the current scaffold to a demo-able product as a sequence of
**phases**. Each phase states a clear goal and the observable capability it unlocks; the detailed
PR breakdown inside a phase is owned by that phase's lead and follows the one-responsibility rule in
[`.claude/rules/git-workflow.md`](./.claude/rules/git-workflow.md). Phases are sequential by
dependency; work within a phase can proceed in parallel.

The target demo is the **Launch Change Commander** scenario green locally, as defined by
[`verify.md`](./verify.md) — it runs without a Microsoft 365 tenant; the live chat entry point is a
deferred extension (see Phase 5).

Status legend: ☐ todo · ◐ in progress · ☑ done.

**How to read a phase:** each phase lists a **Goal**, a **Definition of done** (the demo capability
it unlocks), a coarse **Scope**, an **Owner**, and **Entry criteria**. The owner decomposes the
scope into small, reviewable PRs.

## Phase 1 — Walking skeleton ☐

- **Goal:** a runnable, layered shell of the system that boots and is green in CI.
- **Definition of done:** `uvicorn app.main:app` boots; `GET /api/health` returns healthy;
  `pnpm dev` serves the dashboard; the backend package layout
  (`mcp/ api/ services/ agent/ ports/ adapters/ domain/`) and the frontend app exist; CI is green;
  `docs/` stubs are in place. (Covers the *Preconditions* in `verify.md`.)
- **Scope:** backend skeleton + `config.py`, health endpoint, frontend skeleton, dev tooling
  (`Makefile`, `docker-compose.yml`, `docs/` stubs).
- **Owner:** TBD
- **Entry criteria:** current state.

## Phase 2 — Reasoning core (dry-run, fully mocked) ☐

- **Goal:** the plan → policy → approve → execute → audit engine works end-to-end in dry-run with
  zero external credentials.
- **Definition of done:** submit a decision (`FORCE_ALL_MOCK`, dry-run) → a structured
  `ExecutionPlan` validated against **registered capabilities** → deterministic risk scoring →
  the **approval interrupt suspends the run to a checkpoint** → a resume call executes against mock
  adapters → an **append-only** audit record with before/after snapshots and rollback hints. Durable
  resume across the approval gap is covered by tests. (Covers `verify.md` *Core flow* and
  *Safety & audit* in dry-run.)
- **Scope:** `domain/` models/enums/errors; ports (integration, repository, checkpointer, llm,
  notifier); LangGraph state + nodes + wiring + durable interrupt/resume; adapter base + registry +
  the mock adapters the scenario needs; persistence (db, repositories, SQLite checkpointer).
- **Owner:** TBD
- **Entry criteria:** Phase 1 complete.

## Phase 3 — Operator dashboard (approval UX) ☐

- **Goal:** a human can drive the whole flow from the browser.
- **Definition of done:** a services layer and REST contract (decisions, plans, approvals
  [idempotent], audit, integrations) back a Next.js dashboard that renders the plan + risk with
  approve/reject, shows execution status, displays audit before/after and rollback hints, and shows
  real-vs-mock integration badges. (Covers `verify.md` *Dashboard*.)
- **Scope:** services layer; REST routers; optional SSE status stream; dashboard views (plan review
  & approval, audit log, integration badges); typed API client matching `docs/api-contract.md`.
- **Owner:** TBD
- **Entry criteria:** Phase 2 complete.

## Phase 4 — Real execution over a secured MCP surface ☐

- **Goal:** the same flow is callable by an external agent over an OAuth2-secured MCP server and
  performs at least one real cross-system change.
- **Definition of done:** a real GitHub adapter (milestone/issue) with recorded tests mutates a
  throwaway test repo after approval; the MCP server exposes tools
  (`submit_decision`, `get_plan`, `approve_plan`, `get_status`) and resources, mounted on the FastAPI
  app; an OAuth2 resource server runs with a local dev issuer; MCP `approve_plan` reaches parity with
  the REST approval and is **idempotent** across both surfaces; dry-run remains the safe default.
  (Covers `verify.md` *Approval & execution (live)* and the MCP parity / idempotency checks.)
- **Scope:** GitHub real adapter; remaining mock adapters as needed; MCP server mount + tools +
  resources; OAuth2 resource server + shared security.
- **Owner:** TBD
- **Entry criteria:** Phase 3 complete (REST/services contract stable).

## Phase 5 — Microsoft 365 surface & demo package ☐

- **Goal:** package the headline demo and wire the chat entry point (live-chat verification deferred
  until a Microsoft 365 dev tenant is available).
- **Definition of done:** a declarative agent manifest and an MCP plugin manifest pointing at the MCP
  server; approval rendered as a data-driven **Adaptive Card**; `scripts/seed_demo.py` and
  `scripts/verify.sh` fully green **except** the *Pending tenant* section; a public README, an
  architecture diagram, and a short demo recording. With a dev tenant: the agent installs in
  Microsoft 365 Copilot Chat, calls the MCP server over Entra ID OAuth, and the Adaptive Card's
  approve/reject actions resume the run.
- **Scope:** `m365/` declarative agent + plugin manifests; `m365/adaptive-cards/` approval card;
  demo seed data + script; README / architecture diagram / demo recording; tenant-dependent checks
  tracked as pending.
- **Owner:** TBD
- **Entry criteria:** Phase 4 complete.

## Working agreement (all phases)

- One responsibility per PR, ≤ ~300 substantive lines; refactors kept separate from behavior changes
  (see `git-workflow.md`).
- Trunk (`main`) stays green: builds, lints, type-checks, and tests pass.
- Shipped docs stay product-focused — the docs scope rule in `.claude/rules/docs.md`, enforced by the
  docs check in `scripts/verify.sh`.

## Decisions to record as ADRs

Capture significant choices under `docs/adr/` as they are made:

- Durable interrupt vs. MCP/HTTP statelessness for the approval gap.
- `IntegrationAdapter` port as the integration boundary.
- SQLite-now / Postgres-later, swappable persistence.

## Demo readiness

The system is progressively demoable: the dashboard flow from Phase 3, real execution over MCP from
Phase 4, and the full Launch Change Commander scenario at Phase 5. The pre-demo gate is `verify.md`
fully green, minus its *Pending tenant* section.
