# Verification checklist

End-to-end verification of the **three trials**. This is the pre-demo gate: every item must pass
locally before the demo. It runs without a Microsoft 365 tenant — the chat entry point is verified
separately once a tenant is available (see *Pending tenant* below).

Run the scripted portion with:

```bash
scripts/verify.sh
```

The script automates what it can and prints a PASS/PENDING line per check. The manual checks are
listed below it.

## Preconditions

- ☐ Backend boots: `uvicorn app.main:app` starts with no errors.
- ☐ `GET /api/health` returns healthy.
- ☐ Config sanity: `INTEGRATION_MODE` has GitHub `real` (with `GITHUB_TOKEN` against a throwaway test
  repo) and all other systems `mock`. Alternatively `FORCE_ALL_MOCK=true` for a fully credential-free
  run.

## Trial 1 — Reschedule Sync (dry-run, then live)

- ☐ Submit "move the rehearsal to 2026-06-17" with `run_mode=dry_run`.
- ☐ A **Change Court** is produced: structured change, **impact evidence** (milestone move, calendar
  events, planner shift, pending announcement), a feasible plan with predicted effects, and rollback
  hints.
- ☐ Every plan step references a **registered capability** (no hallucinated actions).
- ☐ **Policy + quorum** flags HIGH risk → status `AWAITING_VERDICT` with the required approvers and
  verdict options (approve / approve internal only / request revision / reject).
- ☐ Dry-run mutates **nothing** external; the audit record is marked `DRY_RUN`.
- ☐ Submit live → cast verdict **approve** via MCP `cast_verdict` → graph resumes from its checkpoint
  and executes.
- ☐ **Real GitHub:** the "Launch Rehearsal" milestone due date is updated in the test repo.
- ☐ Mock adapters return believable before/after snapshots for calendar, planner, and announcement.
- ☐ Final status is `DONE`; the audit log shows before/after and rollback hints (append-only).
- ☐ **Conflict variant:** "move the rehearsal to 2026-06-16" collides with the seeded board review →
  the date is **refused as posed** and the next free day (2026-06-17) is proposed as a safe
  alternative (accept_alternative / request_revision / reject — no plain approve).
- ☐ **Hallucination guard:** adding "also delete the old launch repo" is **rejected** — no registered
  capability supports it; it is neither planned nor executed.
- ☐ **Idempotency:** casting the same verdict twice is a no-op — no double execution (REST and MCP).
- ☐ **Partial failure:** a simulated Planner failure is captured in `errors` and surfaced with a
  rollback suggestion; the run does not crash.

## Trial 2 — Meeting Actions

- ☐ Submit "create action items from standup."
- ☐ Impact evidence: the standup's four spoken follow-ups surface with their owners and dates,
  grounded with a follow-through citation.
- ☐ Plan: three `planner.create_task` steps (owner + due date) and one `outlook.create_event` for
  the review that was proposed without a date.
- ☐ Policy: **LOW** risk, **no approver** — the court auto-approves; with identities configured the
  requester's confirmation at the review gate is what executes.
- ☐ Final status is `DONE`; the audit record carries the created tasks.

## Trial 3 — Weekly Report

- ☐ Submit "post the Project X weekly report."
- ☐ Impact evidence: recently closed GitHub issues, tracked tasks, and the week's meetings —
  collected once, grounded with a reporting-cadence citation. With `github:real`, the closed-issue
  evidence is the repository's actual activity.
- ☐ Plan: one `teams.post_message` composed from the gathered counts.
- ☐ Policy: **LOW** risk, **no approver**; executes on the requester's authority.
- ☐ Final status is `DONE`; the audit record carries the posted report.

## Quality gates

- ☐ `ruff check` and `mypy` clean (backend).
- ☐ `pytest` green (unit + integration, including dry-run and live court paths, and the guard tests).
- ☐ Shipped docs stay product-focused (`.claude/rules/docs.md`): the docs check in `scripts/verify.sh`
  passes.
- ☐ The pipeline run page is read-only and signed-link-gated: no token → 401, secret unset → 404,
  and the page exposes no decision action (verdicts happen only on the card).

## Pending tenant (verify when a Microsoft 365 dev tenant is available)

- ☐ Declarative agent installs and appears in Microsoft 365 Copilot Chat / Teams.
- ☐ The agent calls the MCP server over OAuth 2.0 (Entra ID) and runs a trial.
- ☐ The **Change Court Adaptive Card** renders in chat and its verdict actions resume the run.
- ☐ Real Microsoft Graph writes (Outlook calendar / Planner / SharePoint) replace their mock adapters.
