# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**AI Change Court** — governed execution for risky enterprise decisions in Microsoft Teams. It puts a
risky decision *on trial* before it becomes action: parse the request, gather cross-system **impact
evidence**, generate a feasible plan (or a **safe alternative** when the request is unsafe), resolve
which stakeholders must approve (**quorum**), collect a **verdict**, then execute and keep an
**append-only audit trail**. The differentiator is that it can **refuse an unsafe decision and
propose a safer one**. It is not a chatbot and not a workflow macro.

The court pipeline: **intake → impact → options → policy+quorum → [verdict] → execute → audit**.

## Current status — read first

The repository is **documentation and scaffold only**. There is no `backend/` code yet (no
`pyproject.toml` or source files), and there is **no frontend** — the Teams Adaptive Card is the only
UI. The commands and module paths below are the *intended* shape and only become runnable once the
Phase 1 skeleton lands. Implementation order and PR slicing live in `roadmap.md` (Phases 1–5) and in
GitHub issues (labeled `ready`/`blocked`, `area:*`). Build along that slicing — do not scaffold the
whole tree at once. **Stay convergent:** every change must serve one of the three trials (Launch
Slip, Customer Promise, Vendor Access); see `verify.md`.

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
  Teams Adaptive Card = the only UI (no web dashboard)
  SQLite now → Postgres later (DB_URL-driven)
```

- **Dependency inversion.** `agent/` and `services/` depend on `ports/` *only* — never on an
  integration SDK, SQLAlchemy, or an LLM client directly. Concrete implementations live in
  `adapters/`.
- **One business layer.** MCP tools (`mcp/`) and the minimal REST API (`api/`) are thin façades over
  `services/`. No business logic in routers or tools — no duplication.
- **Pure domain.** `domain/` imports nothing from FastAPI, LangGraph, or any adapter.
- **LangGraph single-agent "Change Court."** Nodes `intake → impact → options → policy+quorum →
  execute → audit`, each state-in/state-out, presented as roles (Prosecutor=impact, Defender=options,
  Clerk=audit, Executor=execute):
  - `intake` — parse into a structured `Change`; validate every requested action against **registered
    capabilities** (hallucination guard — unsupported actions blocked, not planned).
  - `impact` — gather second-order consequences via adapter **read** capabilities → evidence.
  - `options` — feasible plan, or a **safe alternative** when the request is unsafe.
  - `policy+quorum` — deterministic risk → `requires_approval` + required approvers + verdict options;
    rules are data, not code.
  - `execute` — registry → adapter per step; honors `run_mode`.
  - `audit` — append-only before/after + rollback hints + trial record.
- **Verdict is a durable interrupt** (`interrupt_before=["execute"]`), checkpointed by `thread_id`.
  Submit returns immediately; `cast_verdict` rehydrates and resumes. **Never hold the graph in memory
  across the verdict gap.** Casting the same verdict twice is idempotent.
- **Dry-run is a first-class state field**, not a separate code path. `DRY_RUN` returns predicted
  effects with no side effects.
- **Open/Closed adapters.** A new integration = one adapter module implementing `IntegrationAdapter`
  (read + write capabilities) + one `IntegrationRegistry` registration. No edits to the graph,
  services, REST, or MCP. Real-vs-mock is chosen per system from config.
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

There is no frontend. The Teams Adaptive Card is the only UI; audit/trial data is exposed via an MCP
resource (REST is health-only).

End-to-end checklist: `scripts/verify.sh` (verifies the three trials; currently stubbed).

## Configuration & run modes

Env-driven via `config.py` (pydantic-settings) — see `.env.example`. Architecturally significant:

- `INTEGRATION_MODE` — per-system `real`/`mock` selection (default: GitHub `real`, others `mock`).
- `FORCE_ALL_MOCK=true` — run every integration as a mock, with **zero external credentials**.
- `DRY_RUN_DEFAULT` — whether new decisions default to dry-run.
- `DB_URL` — SQLite locally, Postgres later.
- `GITHUB_TOKEN` — only when the GitHub adapter runs in `real` mode. `OAUTH_*` — MCP OAuth2 settings.

GitHub is the one real adapter; the rest (Outlook, Planner, SharePoint, Teams, CRM, Entra) are mocks
returning realistic data, so the system runs fully locally. Only the adapters the three trials need
are built — no ServiceNow / generic Graph adapter.

## Git / PR workflow

- Trunk is `main` and stays green. **PR-first: one issue → one `feat|fix|docs|chore|refactor/<scope>`
  branch → one PR that `Closes #<issue>`** (squash-merge). Direct pushes to `main` are allowed only
  for trivial/urgent fixes. Never force-push or rewrite published history. `main` is protected (PR +
  1 approval required; admin bypass allowed) — while solo, admin-merge a green PR. Pick work from the
  `ready` label; self-assign to claim.
- **One responsibility per PR, ≤ ~300 substantive lines.** Keep refactors separate from behavior
  changes. Follow `roadmap.md` slicing: one adapter / one node / one router per PR.
- Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`), imperative mood.
  Squash-merge; delete the branch after merge.
- CI today: `.github/workflows/security.yml` (gitleaks secret scan) + weekly Dependabot. No secrets
  in the repo — use env vars.

The demo spine is **three trials** — Launch Slip, Customer Promise (reject unsafe promise + safe
alternative), and Vendor Access (ambiguous → least-privilege + auto-revoke). See `verify.md`.
