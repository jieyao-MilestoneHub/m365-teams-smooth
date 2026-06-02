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

## Trial 1 — Launch Slip (dry-run, then live)

- ☐ Submit "slip the launch from 2026-06-10 to 2026-06-17" with `run_mode=dry_run`.
- ☐ A **Change Court** is produced: structured change, **impact evidence** (milestone move, calendar
  conflict, planner shift, pending announcement), a feasible plan with predicted effects, and rollback
  hints.
- ☐ Every plan step references a **registered capability** (no hallucinated actions).
- ☐ **Policy + quorum** flags HIGH risk → status `AWAITING_VERDICT` with the required approvers and
  verdict options (approve / approve internal only / request revision / reject).
- ☐ Dry-run mutates **nothing** external; the audit record is marked `DRY_RUN`.
- ☐ Submit live → cast verdict **approve** via MCP `cast_verdict` → graph resumes from its checkpoint
  and executes.
- ☐ **Real GitHub:** the milestone due date is updated / an issue is created in the test repo.
- ☐ Mock adapters return believable before/after snapshots for calendar, planner, and announcement.
- ☐ Final status is `DONE`; the audit log shows before/after and rollback hints (append-only).
- ☐ **Hallucination guard:** adding "also delete the old launch repo" is **rejected** — no registered
  capability supports it; it is neither planned nor executed.
- ☐ **Idempotency:** casting the same verdict twice is a no-op — no double execution (REST and MCP).
- ☐ **Partial failure:** a simulated Planner failure is captured in `errors` and surfaced with a
  rollback suggestion; the run does not crash.

## Trial 2 — Customer Promise

- ☐ Submit "promise Customer A that SSO is GA by 2026-06-17."
- ☐ Impact evidence: GitHub shows open blocking issues; CRM shows the renewal value and date; the
  security review is scheduled **after** the promised date.
- ☐ Policy: no GA promise before security approval → the requested promise is **unsafe**.
- ☐ **Verdict: reject the unsafe promise**, with a **safe alternative** — private preview on 2026-06-17,
  GA pending the security review on 2026-06-18.
- ☐ On accepting the alternative: a GitHub issue comment (customer due date), an Outlook review event,
  a CRM note ("do not promise GA; offer private preview"), a customer email **draft**, and a Teams
  escalation thread are produced.

## Trial 3 — Vendor Access

- ☐ Submit "give the external vendor access to Project X until the campaign is done."
- ☐ The court flags the **ambiguous duration** and the **over-broad folder scope**.
- ☐ **Proposed safe access:** read-only to `/ProjectX/LaunchAssets` until 2026-06-30, then auto-revoke;
  requires manager approval (and security approval if the folder holds customer data).
- ☐ On approval: an Entra guest invite (mock), a scoped SharePoint permission (mock), an expiry, and an
  auto-revoke task are created; the audit log records the grant and the scheduled revoke.

## Quality gates

- ☐ `ruff check` and `mypy` clean (backend).
- ☐ `pytest` green (unit + integration, including dry-run and live court paths, and the guard tests).
- ☐ Shipped docs stay product-focused (`.claude/rules/docs.md`): the docs check in `scripts/verify.sh`
  passes.

## Pending tenant (verify when a Microsoft 365 dev tenant is available)

- ☐ Declarative agent installs and appears in Microsoft 365 Copilot Chat / Teams.
- ☐ The agent calls the MCP server over OAuth 2.0 (Entra ID) and runs a trial.
- ☐ The **Change Court Adaptive Card** renders in chat and its verdict actions resume the run.
- ☐ Real Microsoft Graph writes (Outlook calendar / Planner / SharePoint) replace their mock adapters.
