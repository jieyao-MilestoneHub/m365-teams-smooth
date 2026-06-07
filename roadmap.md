# Roadmap

This roadmap describes the path from the current scaffold to a demo-able **AI Change Court** as a
sequence of **phases**. Each phase states a clear goal and the observable capability it unlocks; the
detailed PR breakdown inside a phase is owned by that phase's lead and follows the one-responsibility
rule in [`.claude/rules/git-workflow.md`](./.claude/rules/git-workflow.md). Phases are sequential by
dependency; work within a phase can proceed in parallel.

The single success metric is that the **three trials** (below) demo cleanly, end-to-end, in Microsoft
Teams via the Change Court Adaptive Card, as defined by [`verify.md`](./verify.md). It runs without a
Microsoft 365 tenant; the live chat entry point is a deferred extension (Phase 5).

Status legend: ☐ todo · ◐ in progress · ☑ done.

**How to read a phase:** each phase lists a **Goal**, a **Definition of done** (the demo capability
it unlocks), a coarse **Scope**, an **Owner**, and **Entry criteria**. The owner decomposes the scope
into small, reviewable PRs.

## The three trials (the demo spine)

1. **Reschedule Sync** — "move the rehearsal to 2026-06-17." One request moves a real GitHub
   milestone plus mock calendar, planner, and announcement; flagged HIGH risk with an
   `eng_lead` + `comms` quorum. The conflicting-date variant ("…to 2026-06-16", an occupied day) is
   **refused as posed** with the next free day proposed as a safe alternative. An unsupported request
   ("delete the repo") is blocked by the capability registry; a simulated step failure yields a
   partial result with a rollback hint; casting the same verdict twice is a no-op.
2. **Meeting Actions** — "create action items from standup." The discussion's spoken follow-ups
   become tracked tasks with owners and due dates, plus a scheduled review for the undated proposal.
   LOW risk, no approver — the requester's confirmation executes it.
3. **Weekly Report** — "post the Project X weekly report." Recently closed issues, tracked tasks,
   and the week's meetings are aggregated into one post to the project channel; with the real GitHub
   adapter the evidence is the repository's actual activity.

The earlier governance trials (customer promise, vendor access) remain wired and tested as
additional court capabilities beyond the demo spine.

## Phase 1 — Walking skeleton ☑

- **Goal:** a runnable, layered backend shell that boots and is green in CI.
- **Definition of done:** `uvicorn app.main:app` boots; `GET /api/health` returns healthy; the
  backend package layout (`mcp/ api/ services/ agent/ ports/ adapters/ domain/`) exists; CI is green;
  `docs/` (incl. `docs/adr/`) stubs are in place.
- **Scope:** backend skeleton + `config.py`, health endpoint, dev tooling (`Makefile`,
  `docker-compose.yml`, docs stubs). No frontend.
- **Owner:** TBD · **Entry:** current state.

## Phase 2 — Court engine (dry-run, fully mocked) ☑

- **Goal:** the court pipeline runs end-to-end in dry-run with zero external credentials.
- **Definition of done:** a submitted change flows `intake → impact → options → policy+quorum →
  [verdict interrupt] → execute → audit` under `FORCE_ALL_MOCK`, producing impact evidence, verdict
  options, and an **append-only** audit record; the run **suspends to a checkpoint** at the verdict
  gate and **resumes** on a cast verdict (tested). The **hallucination guard** (intake) and
  **idempotency** (verdict) are covered by tests.
- **Scope:** `domain/` (Change, ImpactEvidence, ExecutionPlan/Step, RiskResult, Quorum/Approver, Verdict,
  Capability); ports (integration with read+write capabilities, repository, checkpointer, llm,
  notifier); the court nodes + graph wiring + verdict interrupt/resume; adapter base + registry + the
  mock adapters the trials need; persistence (db, repositories, SQLite checkpointer).
- **Owner:** TBD · **Entry:** Phase 1.

## Phase 3 — Trials & governance intelligence ☑

- **Goal:** the differentiators — the court detects impact, proposes safe alternatives, resolves
  quorum, and wires the three trials.
- **Definition of done:** each trial yields the expected Change Court card data and verdict, including
  **UC2 reject-unsafe-promise + safe alternative** and **UC3 ambiguous → least-privilege + auto-revoke**;
  failure-injection and the hallucination guard pass against golden fixtures.
- **Scope:** impact gatherers (read capabilities), safe-alternative generator, quorum/approver resolver +
  verdict-option derivation, policy rule packs; the three trial flows; golden fixtures + guard tests.
- **Owner:** TBD · **Entry:** Phase 2.

## Phase 4 — Real execution + secured MCP ☑

- **Goal:** the court is callable by an external agent over an OAuth2-secured MCP server and performs
  at least one real cross-system change.
- **Definition of done:** a real GitHub adapter (read blockers + write milestone/issue) mutates a
  throwaway repo after a verdict; the MCP server exposes tools (`submit_change`, `get_trial`,
  `cast_verdict`, `get_status`) and resources (trial / audit / capabilities), mounted on FastAPI; an
  OAuth2 resource server runs with a local dev issuer; `cast_verdict` reaches parity with REST and is
  idempotent across both surfaces.
- **Scope:** GitHub real adapter; MCP server mount + tools + resources; OAuth2 resource server + shared
  security.
- **Owner:** TBD · **Entry:** Phase 3.

## Phase 5 — Teams surface & demo package ◐

- **Status:** the local scope (manifests, Adaptive Cards, demo seed scripts, docs) is complete and
  `scripts/verify.sh` is green; the **Microsoft 365 tenant sideload — live chat in Copilot/Teams and
  real Microsoft Graph writes — is the only remaining blocker**, tracked as the *Pending tenant*
  section of [`verify.md`](./verify.md).
- **Goal:** package the three-trial demo and wire the chat entry point (live-chat verification deferred
  until a Microsoft 365 dev tenant is available).
- **Definition of done:** a declarative agent manifest + plugin manifest pointing at the MCP server;
  the **Change Court Adaptive Card** (proposed change · impact evidence · required approvers · verdict
  buttons) + a verdict-result card; seed/demo scripts for the three trials; `scripts/verify.sh` green
  **except** the *Pending tenant* section; README, architecture diagram, and a short demo recording.
- **Scope:** `m365/` manifests; `m365/adaptive-cards/` cards; demo seed scripts; README/diagram/
  recording; tenant-dependent checks tracked as pending.
- **Owner:** TBD · **Entry:** Phase 4.

## Working agreement (all phases)

- One responsibility per PR, ≤ ~300 substantive lines; refactors separate from behavior changes
  (`git-workflow.md`).
- Trunk (`main`) stays green: builds, lints, type-checks, and tests pass.
- Shipped docs stay product-focused (`.claude/rules/docs.md`), enforced by the docs check in
  `scripts/verify.sh`.
- **Stay convergent:** every PR must serve one of the three trials. Non-goals: no web dashboard, no
  full multi-agent runtime, no real integrations beyond GitHub, no adapters beyond the seven the
  trials need.

## Decisions to record as ADRs

- Durable verdict interrupt vs. MCP/HTTP statelessness for the approval gap.
- `IntegrationAdapter` port (read + write capabilities) as the integration boundary.
- SQLite-now / Postgres-later, swappable persistence.

## Demo readiness

The pre-demo gate is `verify.md` fully green, minus its *Pending tenant* section. The three trials are
the only thing that has to shine.
