# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**AI Change Court** — governed execution for risky enterprise decisions in Microsoft Teams. It puts a
risky decision *on trial* before it becomes action: parse the request, gather cross-system **impact
evidence**, generate a feasible plan (or a **safe alternative** when the request is unsafe), resolve
which stakeholders must approve (**quorum**), collect a **verdict**, then execute and keep an
**append-only audit trail**. The differentiator is that it can **refuse an unsafe decision and
propose a safer one**. It is not a chatbot and not a workflow macro.

The court pipeline: **intake → impact → options → policy+quorum → [verdict] → execute → verify → audit**.

## Current status — read first

The backend engine is **implemented and runs end-to-end locally, credential-free**. `backend/` holds
the full layered app (`agent/ mcp/ api/ services/ ports/ adapters/ domain/`), the LangGraph court
pipeline, SQLAlchemy persistence, and a green test suite; the headline demo and its additional
capabilities pass under `scripts/verify.sh`. GitHub is the one real integration; the other six
systems are mocks. There is
**no frontend build** — the Teams Adaptive Card is the decision UI, rendered tenant-free via the
Playground bot or the exported card JSON; the one web surface is a read-only, signed-link-gated
pipeline **run page** (a static file the backend serves — it inspects a trial's run, never decides).
The commands and module paths below are runnable today.

What remains is **going live in a real tenant** (the *Pending tenant* items in `scripts/verify.sh`):
hosting the backend over public HTTPS, Entra ID OAuth2, sideloading the declarative agent, and —
optionally — replacing the mocks with real Microsoft Graph adapters. Phases and PR slicing live in
GitHub issues (labeled `ready`/`blocked`, `area:*`); keep PRs single-responsibility. **Stay
convergent:** every change must serve the headline demo (**Informed Approval** — the Reschedule
scenario, the only one recorded) or the additional capabilities the same engine already handles
(Meeting Actions, Weekly Report, Customer Promise, Vendor Access — wired and tested, runnable but not
recorded).

## Source of truth: `.claude/rules/`

Read these before non-trivial work — they are the standing engineering contract, and this file only
summarizes them:

- `architecture.md` — layering, the LangGraph agent, adapter/registry design, persistence.
- `coding-style.md` — Python/TS conventions, typing, testing expectations.
- `git-workflow.md` — branching, PR size, commit conventions.
- `docs.md` — **hard rule:** all shipped/public text (README, docstrings, code comments,
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
  Teams Adaptive Card = the only DECISION UI; the read-only run page
  (signed links, /runs/{thread_id}) is the one web surface — no dashboard
  SQLite now → Postgres later (DB_URL-driven)
```

- **Dependency inversion.** `agent/` and `services/` depend on `ports/` *only* — never on an
  integration SDK, SQLAlchemy, or an LLM client directly. Concrete implementations live in
  `adapters/`.
- **One business layer.** MCP tools (`mcp/`) and the minimal REST API (`api/`) are thin façades over
  `services/`. No business logic in routers or tools — no duplication.
- **Pure domain.** `domain/` imports nothing from FastAPI, LangGraph, or any adapter.
- **LangGraph single-agent "Change Court."** Nodes `intake → impact → options → policy+quorum →
  execute → verify → audit`, each state-in/state-out, presented as roles (Prosecutor=impact,
  Defender=options, Clerk=audit, Executor=execute):
  - `intake` — parse into a structured `Change`; validate every requested action against **registered
    capabilities** (hallucination guard — unsupported actions blocked, not planned).
  - `impact` — gather second-order consequences via adapter **read** capabilities → evidence.
  - `options` — feasible plan, or a **safe alternative** when the request is unsafe.
  - `policy+quorum` — deterministic risk → `requires_approval` + required approvers + verdict options;
    rules are data, not code.
  - `execute` — registry → adapter per step; honors `run_mode`.
  - `verify` — checks the live writes against the reviewed plan (agentic when an LLM is configured).
  - `audit` — append-only before/after + rollback hints + trial record.
- **Verdict is a durable interrupt** (`interrupt_before=["execute"]`), checkpointed by `thread_id`.
  Submit returns immediately; `cast_verdict` rehydrates and resumes. **Never hold the graph in memory
  across the verdict gap.** Casting the same verdict twice is idempotent.
- **Dry-run is a first-class state field**, not a separate code path. `DRY_RUN` returns predicted
  effects with no side effects.
- **Open/Closed adapters.** A new integration = one adapter module implementing `IntegrationAdapter`
  (read + write capabilities) + one `IntegrationRegistry` registration. No edits to the graph,
  services, REST, or MCP. Real-vs-mock is chosen per system from config.
- **LLM calls are governed.** The `LLMProvider` port carries caching + structured-output intent
  (`LlmRequest`) and returns per-call usage telemetry (`LlmResult`); structured output is native
  strict JSON Schema with a typed failure (`LlmOutputError`) and a deterministic fallback at every
  call site; untrusted content is screened (`GuardrailPort`) and fenced before any LLM reasons over
  it. Portability seams and deliberately deferred hardening: ADR-0013.
- **Audit is append-only** — never updated. Rollback hints are advisory data, never auto-executed.

When you make a significant design choice (e.g. the interrupt-vs-statelessness decision), record it
as an ADR under `docs/adr/`.

## Commands

Backend (FastAPI, Python 3.11+, `uv`):

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload   # REST health only (/api/health)
uv run uvicorn app.asgi:app --reload   # REST + the OAuth2-protected MCP server at /mcp
uv run ruff check                      # lint
uv run mypy                            # type-check
uv run pytest                          # tests
uv run pytest path/to/test.py::test_name   # single test
```

Common workflows from the repo root (all fully mocked / credential-free):

```bash
make demo            # run the headline (Informed Approval) end-to-end (make demo-all adds the rest)
make check           # ruff + mypy + pytest
make bot             # clickable Change Court card via the Playground bot (tenant-free)
make cards           # export the headline Adaptive Card JSON (make cards-all for every capability)
scripts/verify.sh    # full gate: trials + safety + MCP + quality (tenant checks report PENDING)
```

There is no frontend build. The Teams Adaptive Card is the only decision UI; audit/trial data is
exposed via an MCP resource. REST serves health plus the read-only run page (`/runs/{thread_id}` +
its poll endpoint, HMAC-signed links, no mutating action — see ADR-0011). The MCP surface is
implemented in `backend/app/mcp/`: tools `submit_change`, `get_status`, `get_trial`,
`send_for_approval`, `decide`, `cast_verdict`, `withdraw_change`, `list_pending_approvals`,
`acknowledge_outcome`, plus resources for trial / audit / capabilities. `cast_verdict` and `decide`
hold idempotent parity across both MCP and REST. Package the M365 app with `make package`.

## Configuration & run modes

Env-driven via `config.py` (pydantic-settings) — see `.env.example`. Architecturally significant:

- `INTEGRATION_MODE` — per-system `real`/`mock` selection (default: GitHub `real`, others `mock`).
- `FORCE_ALL_MOCK=true` — run every integration as a mock, with **zero external credentials**.
- `DRY_RUN_DEFAULT` — whether new decisions default to dry-run.
- `DB_URL` — SQLite locally, Postgres later.
- `GITHUB_TOKEN` — only when the GitHub adapter runs in `real` mode. `OAUTH_*` — MCP OAuth2 settings.
- `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` — set both to enable the real LLM provider
  (keyless `DefaultAzureCredential` unless `LLM_API_KEY` is set); leave empty for the offline fake
  LLM provider (the default for local development and fully-mocked runs). `LLM_TIMEOUT_SECONDS` /
  `LLM_MAX_RETRIES` / `LLM_MAX_TOKENS` bound every call; `CONTENT_SAFETY_ENDPOINT` switches the
  guardrail from the offline heuristic to Azure Prompt Shields.

GitHub is the one real adapter; the rest (Outlook, Planner, SharePoint, Teams, CRM, Entra) are mocks
returning realistic data, so the system runs fully locally. Only the adapters the headline and its
additional capabilities need are built — no ServiceNow / generic Graph adapter.

## Git / PR workflow

- Trunk is `main` and stays green. **PR-first: one issue → one `feat|fix|docs|chore|refactor/<scope>`
  branch → one PR that `Closes #<issue>`** (squash-merge). Direct pushes to `main` are allowed only
  for trivial/urgent fixes. Never force-push or rewrite published history. `main` is protected (PR +
  1 approval required; admin bypass allowed) — while solo, admin-merge a green PR. Pick work from the
  `ready` label; self-assign to claim.
- **One responsibility per PR, ≤ ~300 substantive lines.** Keep refactors separate from behavior
  changes. Follow single-responsibility slicing: one adapter / one node / one router per PR.
- Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`), imperative mood.
  Squash-merge; delete the branch after merge.
- CI today: `.github/workflows/security.yml` (gitleaks secret scan) + weekly Dependabot. No secrets
  in the repo — use env vars.

The demo spine is **one headline scenario — Informed Approval** (the Reschedule scenario): one
request moves the GitHub milestone, the Outlook calendar, the Planner tasks, and the Teams
announcement together; a conflicting date is refused and a free one proposed. It is the only scenario
recorded, and `make demo` runs only it. The same engine already handles four **additional
capabilities** — Meeting Actions (standup follow-ups become tracked tasks on the requester's
authority), Weekly Report (scattered activity aggregated into one post), and the governance trials
Customer Promise and Vendor Access (refuse-and-propose-safer). They stay wired and tested, runnable
via `make demo-all` or the Playground bot, but are not part of the recorded headline — present them
as capabilities the architecture supports, not as demos to build out. See `docs/demo/`.
