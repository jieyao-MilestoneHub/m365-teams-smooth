# Demo-day checklist

Operational guardrails for walking the live deployment through the **Informed Approval** headline
(and the two-user approval flow) without self-inflicted surprises. The credential-free local path
(`make demo`, the Playground bot) needs none of this — this page is for the deployed instance.

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
   → the approver's proactive card and activity toast arrive → verdict → DRY_RUN execution → the
   audit record and the signed run-page link both open.
4. Tail the logs while doing it: `az containerapp logs show -n changecourt -g changecourt-rg
   --follow` — `notify.sent`, `proactive.create`, and `llm.call` lines confirm each leg.

## The two-user separation-of-duties walk

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
4. The run resumes from its durable checkpoint and executes (honoring `DRY_RUN`); both parties see
   the outcome card.
5. Close on the **append-only audit record** (evidence, approvers, verdict, before/after, rollback
   hints) and the read-only run page on a second screen.

## Recording

- Record the headline scenario only (see [the demo script](./README.md)); keep it under five
  minutes: one sentence in → impact evidence → refusal + safe alternative → informed verdict →
  execution → audit.
- Capture the run page on a second screen for the execution beats.
- Do a full silent dry run immediately before recording; if anything misfires, fix, re-verify the
  *After the final pre-demo deploy* list, and only then record.
