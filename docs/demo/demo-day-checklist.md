# Demo-day checklist

Operational guardrails for walking the live deployment through the headline — the **ticket
demo** (analysis-only evidence packet onto the ticket, then the escalation with its approval
flow) — without self-inflicted surprises. The credential-free local path
(`make demo-ticket`, `make demo`, the Playground bot) needs none of this — this page is for the
deployed instance.

## Freeze the deployment

- **No `terraform apply` and no `az containerapp update` during the demo window.** Any of them
  rolls a new Container App revision, which restarts the app mid-trial.
- The database lives on the persistent `/data` Azure Files mount (`DB_URL`), so trials,
  checkpoints, the audit log, run-page links, and the bot's conversation references **survive a
  revision roll** — the freeze is about avoiding restarts at the wrong moment, not data loss.
- Land every change (image, env, secrets) well before the window, then verify below.

## After the final pre-demo deploy

1. `curl https://<public-base-url>/api/health` returns OK.
2. **Each participant sends the bot one direct message** so its conversation reference is captured
   (once per identity — references persist across deploys; a brand-new database starts empty).
3. Run one throwaway trial end to end: submit → the Change Court card renders → send for approval
   → the approver's proactive card and activity toast arrive → verdict → execution (real writes —
   `DRY_RUN_DEFAULT=false` on the live backend) → the audit record and the signed run-page link
   both open. Reset afterward (below).
4. Tail the logs while doing it: `az containerapp logs show -n changecourt -g changecourt-rg
   --follow` — `notify.sent`, `proactive.create`, and `llm.call` lines confirm each leg.

## The ticket pre-flight (Scenes 1–2)

1. **Reset the demo data before each take** (from `backend/`, env loaded):
   ```bash
   set -a && . ./.env && set +a && uv run python -m scripts.setup_demo --apply --force
   ```
   (equivalent: `make setup-demo-reset`). It restores the GitHub milestone and ticket #440, the
   seeded Outlook calendar (including any event a prior take's execution created), and the
   SharePoint freeze calendar, and clears #440's prior evidence comments. Confirm the audit table
   shows every resource present.
2. The evidence receiver is **already deployed** alongside the backend (an internal Container App
   targeting issue #440), so an analysis-only run from Copilot posts the
   **"Impact analysis — nothing executed"** comment to #440 automatically — no local receiver to
   start. (For the credential-free *local* demo instead, run a local receiver and the ticket demo
   driver — see [README.md](./README.md).)

## The separation-of-duties escalation (Scene 3)

Prerequisites: `APPROVER_DIRECTORY` maps the quorum roles (`eng_lead`, `comms`, `account_owner`,
…) to the **approver's Entra object id** (the directory keys on oid, not UPN), and the requester
signs in as a different, low-privilege account.

1. **Requester** (low-privilege) in Copilot Chat: submit the change — e.g. *"move the launch
   rehearsal to 2026-06-22"* — review the impact evidence and the safe alternative, then send for
   approval with a note.
2. Show the gate: the **requester cannot cast the verdict** — self-approval is rejected, and the
   verdict options live only on the approver's card.
3. **Approver** pulls their pending approvals, opens the Change Court card (proactive bot chat or
   the activity-feed toast), and decides — approving the safe alternative.
4. The run resumes from its durable checkpoint and executes — real writes on the live backend
   (`DRY_RUN_DEFAULT=false`), with a link to each updated resource; both parties see the outcome
   card.
5. Close on the **append-only audit record** (evidence, approvers, verdict, before/after, rollback
   hints) and the read-only run page on a second screen.

## Recording

- Follow the scene-by-scene narration and the Copilot bring-up checks in
  [recording-script.md](./recording-script.md) — Microsoft 365 Copilot Chat is the primary surface.
- Record the headline scenario only (see also [the demo script](./README.md)); keep it under five
  minutes: the ticket and its missing evidence → the analysis-only packet lands as a comment
  (would-be approvers; nothing executed) → escalation: refusal + safe alternative → informed
  verdict → step-by-step execution → audit, with the decision comments arriving on the same
  ticket.
- Capture the run page on a second screen for the execution beats.
- Do a full silent dry run immediately before recording; if anything misfires, fix, re-verify the
  *After the final pre-demo deploy* list, and only then record.
