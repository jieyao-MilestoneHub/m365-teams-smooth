# Verification checklist

End-to-end verification of the **Launch Change Commander** scenario. This is the pre-demo gate:
every item must pass locally before the demo. It runs without a Microsoft 365 tenant — the chat
entry point is verified separately once a tenant is available (see *Pending tenant* below).

Run the scripted portion with:

```bash
scripts/verify.sh
```

The script automates what it can and prints a PASS/PENDING line per check. The manual UI checks are
listed below it.

## Preconditions

- ☐ Backend boots: `uvicorn app.main:app` starts with no errors.
- ☐ `GET /api/health` returns healthy.
- ☐ Frontend boots: `pnpm dev` serves the dashboard.
- ☐ Config sanity: `INTEGRATION_MODE` has GitHub `real` (with `GITHUB_TOKEN` set against a
  throwaway test repo) and all other systems `mock`. Alternatively `FORCE_ALL_MOCK=true` for a
  fully credential-free run.

## Core flow (dry-run first)

- ☐ Seed the sample decision (launch slips from 6/10 to 6/17): `python scripts/seed_demo.py` or
  `POST /api/decisions` with `run_mode=dry_run`.
- ☐ A structured **execution plan** is produced: GitHub milestone/issue update + calendar + planner
  + announcement steps, each with a predicted effect.
- ☐ Every plan step references a **registered capability** (no hallucinated actions).
- ☐ **Policy** flags the plan as requiring approval → status `AWAITING_APPROVAL`.
- ☐ Dry-run mutates **nothing** external; the audit record is marked `DRY_RUN`.

## Approval & execution (live)

- ☐ Submit the decision in live mode → status `AWAITING_APPROVAL`.
- ☐ Approve via REST: `POST /api/decisions/{id}/approval {approved:true}` → graph resumes from its
  checkpoint and executes.
- ☐ Approve via the **MCP tool** `approve_plan` resumes an equivalent run (parity between surfaces).
- ☐ **Real GitHub:** the milestone due date is updated / an issue is created in the test repo.
- ☐ Mock adapters return believable before/after snapshots for the other systems.
- ☐ Final status is `DONE`.

## Safety & audit

- ☐ The **audit log** shows each step with before/after and a rollback hint (`GET /api/audit/{id}`).
- ☐ Audit records are append-only (no in-place updates).
- ☐ **Idempotency:** approving an already-resumed decision is a no-op — no double execution
  (verify via both REST and MCP).
- ☐ A simulated step failure is captured in `errors` and surfaced with a rollback suggestion.

## Dashboard

- ☐ The run appears in the dashboard with its current status.
- ☐ The plan review screen renders the plan + risk and offers approve/reject.
- ☐ The audit view shows before/after and rollback hints.
- ☐ Integration badges correctly show GitHub as `real` and others as `mock`.

## Quality gates

- ☐ `ruff check` and `mypy` clean (backend).
- ☐ `pytest` green (unit + integration, including dry-run and live graph paths).
- ☐ Frontend `pnpm lint` and `pnpm build` succeed.
- ☐ Shipped docs stay product-focused (the docs scope rule in `.claude/rules/docs.md`): the docs
  check in `scripts/verify.sh` passes.

## Pending tenant (verify when a Microsoft 365 dev tenant is available)

- ☐ Declarative agent installs and appears in Microsoft 365 Copilot Chat / Teams.
- ☐ The agent calls the MCP server over OAuth 2.0 (Entra ID) and runs the full flow.
- ☐ The approval **Adaptive Card** renders in chat and its Approve/Reject actions resume the run.
- ☐ Real Microsoft Graph writes (Outlook calendar / Planner) replace their mock adapters.
