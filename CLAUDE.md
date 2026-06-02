# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A decision-to-action agent. It reads a team decision ("slip the launch a week", "grant the
contractor two weeks of access"), produces a reviewable **cross-system execution plan**, runs it
only after human approval, and keeps an **append-only audit trail** with rollback hints. It is not a
chatbot — it is an action layer: **plan → policy → approve → execute → audit**.

## Current status — read first

The repository is **documentation and scaffold only**. There is no `backend/` or `frontend/` code
yet (no `pyproject.toml`, `package.json`, or source files). The commands and module paths below are
the *intended* shape and only become runnable once the M0 scaffold lands. Implementation order and
PR slicing live in `roadmap.md` (milestones M0–M8). Build along that slicing — do not scaffold the
whole tree at once.

## Source of truth: `.claude/rules/`

Read these before non-trivial work — they are the standing engineering contract, and this file only
summarizes them:

- `architecture.md` — layering, the LangGraph agent, adapter/registry design, persistence.
- `coding-style.md` — Python/TS conventions, typing, testing expectations.
- `git-workflow.md` — branching, PR size, commit conventions.
- `docs.md` — **hard rule:** all shipped/public text (README, roadmap, docstrings, code comments,
  commit messages, PR descriptions, M365 manifests, and *this file*) describes **function and
  architecture only**. `.claude/rules/` also holds gitignored, internal-only guidance whose subject
  must never appear in any shipped text. Before committing docs, run the self-check grep defined in
  `docs.md`.

## Architecture — the non-negotiable boundaries

These are easy to violate and load-bearing; keep them intact.

```
M365 Copilot Chat / Teams
  └─ Declarative Agent (m365/)         MCP + OAuth2
        ▼
  FastAPI (backend/)
     mcp/  api/  services/  agent/  ports/  adapters/  domain/
  Next.js dashboard (frontend/)
  SQLite now → Postgres later (DB_URL-driven)
```

- **Dependency inversion.** `agent/` and `services/` depend on `ports/` *only* — never on an
  integration SDK, SQLAlchemy, or an LLM client directly. Concrete implementations live in
  `adapters/`.
- **One business layer.** REST routers (`api/`) and MCP tools (`mcp/`) are thin façades over
  `services/`. No business logic in routers or tools — no duplication between the two surfaces.
- **Pure domain.** `domain/` imports nothing from FastAPI, LangGraph, or any adapter.
- **LangGraph single-agent.** Nodes `plan → policy → execute → audit`, each state-in/state-out:
  - `plan` — LLM extracts a plan; every step validated against **registered adapter capabilities**
    (never trust raw LLM output — constrain it to capability schemas).
  - `policy` — deterministic risk scoring → `requires_approval`; rules are data, not code.
  - `execute` — registry → adapter per step; honors `run_mode`.
  - `audit` — append-only before/after snapshot + rollback hints.
- **Approval is a durable interrupt** (`interrupt_before=["execute"]`), checkpointed by `thread_id`.
  The submit request returns immediately; a later approval call rehydrates from the checkpointer and
  resumes. **Never hold the graph in memory across the approval gap.**
- **Dry-run is a first-class state field**, not a separate code path. `DRY_RUN` returns predicted
  effects with no side effects.
- **Open/Closed adapters.** A new integration = one adapter module implementing `IntegrationAdapter`
  + one `IntegrationRegistry` registration. No edits to the graph, services, REST, or MCP. Real-vs-
  mock is chosen per system from config.
- **Audit is append-only** — never updated. Rollback hints are advisory data, never auto-executed.

When you make a significant design choice (e.g. the interrupt-vs-statelessness decision), record it
as an ADR under `docs/adr/`.

## Commands (intended — require the scaffold to exist)

Backend (FastAPI, Python 3.11+, `uv`):

```bash
cd backend
uv sync
uvicorn app.main:app --reload      # run
uv run ruff check                  # lint
uv run mypy                        # type-check
uv run pytest                      # tests
uv run pytest path/to/test.py::test_name   # single test
```

Frontend (Next.js, TypeScript, `pnpm`):

```bash
cd frontend
pnpm install
pnpm dev
pnpm lint
pnpm build
```

End-to-end checklist: `scripts/verify.sh` (currently stubbed against M0–M7).

## Configuration & run modes

Env-driven via `config.py` (pydantic-settings) — see `.env.example`. Architecturally significant:

- `INTEGRATION_MODE` — per-system `real`/`mock` selection (default: GitHub `real`, others `mock`).
- `FORCE_ALL_MOCK=true` — run every integration as a mock, with **zero external credentials**.
- `DRY_RUN_DEFAULT` — whether new decisions default to dry-run.
- `DB_URL` — SQLite locally, Postgres later.
- `GITHUB_TOKEN` — only when the GitHub adapter runs in `real` mode. `OAUTH_*` — MCP OAuth2 settings.

GitHub is the one real adapter; the rest (Outlook, Planner, Graph, CRM, ServiceNow, SharePoint,
Entra) are mocks returning realistic data, so the system runs fully locally.

## Git / PR workflow

- Trunk is `main` and stays green. **At the current solo stage, commit and push directly to `main`**
  (no PR or branch protection required); never force-push or rewrite published history. The
  `feat|fix|docs|chore|refactor/<scope>` branch + PR workflow in `git-workflow.md` is the target for
  when collaborators join.
- **One responsibility per PR, ≤ ~300 substantive lines.** Keep refactors separate from behavior
  changes. Follow `roadmap.md` slicing: one adapter / one node / one router per PR.
- Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`), imperative mood.
  Squash-merge; delete the branch after merge.
- CI today: `.github/workflows/security.yml` (gitleaks secret scan) + weekly Dependabot. No secrets
  in the repo — use env vars.

The first end-to-end scenario is **Launch Change Commander**: a launch-date change updating a GitHub
milestone/issue plus mock calendar, planner, and announcements.
