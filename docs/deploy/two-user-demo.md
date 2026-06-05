# Two-user approval walkthrough (separation of duties)

How to exercise the approval-routing flow — a low-privilege requester submits a risky change, a
distinct approver decides — first locally in the Agents Playground, then in a real Microsoft 365
tenant. The same steps double as the onboarding runbook for a new environment: register the app,
configure the approver directory, verify the negative cases.

## How the flow works

```
requester: submit ──► AWAITING_REQUESTER_REVIEW ── send (note required) ──► AWAITING_APPROVAL
                                   │                                              │
                                   └── give up ──► WITHDRAWN          approver: decide
                                                                       ├─ approve (quorum) ──► EXECUTE ──► AUDIT
                                                                       └─ reject (note required) ──► REJECTED
```

- Identity comes from the authenticated caller: the MCP access token's claims, or the bot activity's
  sender. The requester can never approve their own change (`separation_of_duties`); only identities
  the **approver directory** maps to a required role may decide (`unauthorized_approver`).
- The directory is env-driven: `APPROVER_DIRECTORY="role:identity,role:identity"`, where identity is
  an Entra object id or UPN (in the Playground, the switchable user's id). Roles: `eng_lead`,
  `security_lead`, `account_owner`, `manager`, `comms`. The env-driven directory is the default
  implementation — an enterprise can swap in a Graph/HR-backed source without touching the service.
- Enforcement engages only when the directory is configured; without it the legacy single-verdict
  flow is unchanged, so the flow can be introduced gradually.

## Local: Agents Playground

1. Pick the identities. The Playground's user switcher changes the channel account id; the launch
   slip trial requires `eng_lead` **and** `comms` (quorum policy `all`), so map two approver users:

   ```bash
   APPROVER_DIRECTORY="eng_lead:<user-b-id>,comms:<user-c-id>" make bot
   ```

2. As **user A**: type `slip the launch from 2026-06-10 to 2026-06-17` → the card holds at
   requester review → fill the note → **Send for approval**.
3. Switch to **user B**: type `queue` → open the trial → **Approve** (quorum still pending).
4. Switch to **user C**: `queue` → **Approve** → the run resumes, executes (DRY_RUN) and audits.
5. Negative checks that must hold:
   - As user A, clicking **Approve** on A's own trial renders the separation-of-duties refusal.
   - **Reject** with an empty note renders "a note is required when rejecting".
   - A user not in the directory sees an empty `queue` and cannot decide.

## Real tenant (Copilot Chat / Teams)

Prerequisites: the backend deployed over HTTPS with Entra OAuth (see [deploy.md](deploy.md)), the
declarative agent sideloaded (see [../m365/README.md](../../m365/README.md)). Before walking the
flow, read the [runbook's Known issues](runbook.md#known-issues-open--plan-around-these) — the
notification toast is not actionable yet, and app-package updates require each user to remove and
re-add the agent.

1. **Entra app registration** in the sign-in tenant: Application ID URI `api://<app-id>`, scope
   `court.use`; the backend's `OAUTH_ISSUER`/`OAUTH_JWKS_URL`/`OAUTH_AUDIENCE` point at this tenant
   and app. Register the Teams OAuth connection and package with its `OAUTH_CONNECTION_ID`.
2. **Create a low-privilege requester account** (no admin roles, Copilot access only) alongside the
   approver account.
3. **Configure the directory** on the deployed backend with the approver's Entra identity:

   ```bash
   APPROVER_DIRECTORY="eng_lead:<approver-oid-or-upn>,comms:<approver-oid-or-upn>"
   ```

   (One person may hold several roles in the directory, but a quorum of multiple roles still needs
   distinct people — one identity contributes at most one approval.)
4. **Walk the flow:** requester signs in to Copilot Chat → submits the change → card holds at
   self-review → sends with a note. Approver signs in → `list_pending_approvals` shows the trial →
   approves → execution (DRY_RUN per ADR-0007) → audit record.
5. **Verify the negative cases** as in the Playground: the requester cannot approve their own
   change, and an account outside the directory cannot decide — there is no path that bypasses the
   configured approver.

## Where each step's data lives

The flow is **change → notify → confirm**; each stage reads or writes a concrete store:

- **Submit (impact evidence)** — gathered live per trial: GitHub milestone/blocker issues and the
  Outlook calendar through the real adapters; Planner tasks and Teams announcements from mocks
  (`integration_mode` decides per system). Nothing is cached between trials.
- **Pending queue** — `list_pending_approvals` reads the court's own `pending_approvals` table
  (written on send, cleared on decision/verdict); it never queries an external system.
- **Execution** — on approval the run resumes and each plan step is routed through the registry to
  its adapter. `run_mode=live` applies the change (e.g. the GitHub milestone due date is actually
  PATCHed); the default dry-run returns predicted effects only. Step results, before-snapshots, and
  rollback hints land in the trial and the append-only audit record.
- **Notify** — the decision toast carries the execution outcome (steps applied/predicted, first
  failure); delivery is best-effort and never blocks the trial.
- **Confirm** — the requester's `acknowledge_outcome` appends an `ACK` event to the approval
  ledger, flips `acknowledged` in the trial summary, and pushes a toast to whoever decided, so all
  parties demonstrably agree on what changed.
- **Inspect** — `court://trial/{thread_id}` (full trial incl. results) and
  `court://audit/{audit_id}` (before/after + rollback hints) expose everything above read-only.
