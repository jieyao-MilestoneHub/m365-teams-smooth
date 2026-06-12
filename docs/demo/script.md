# Demo script — screens ↔ narration

One recording, about five minutes, in a live Microsoft 365 tenant. Two signed-in identities drive
it: **Robin (requester)** and **Alex (approver — the directory grants Alex the quorum roles)**.
The throughline: *every change gets the same automatic impact analysis; almost no change gets an
extra approver.*

## Pre-flight checklist

- Backend deployed over public HTTPS; the declarative agent sideloaded; the bot registered.
- Environment: `APPROVER_DIRECTORY` maps `eng_lead`/`comms`/`account_owner`/`security_lead`/
  `manager` to Alex's UPN; `NOTIFY_MODE=teams`; `RUN_LINK_SECRET` set; `DRY_RUN_DEFAULT=false`;
  `INTEGRATION_MODE=github:real,outlook:real,sharepoint:real,teams:real` (CRM, Planner, and Entra
  stay mocked — the narration never claims otherwise); `EVIDENCE_WEBHOOK_URL` pointing at the
  evidence receiver (`backend/scripts/evidence_receiver.py`, exposed via a dev tunnel or deployed
  alongside).
- Seeds: the GitHub `Launch Rehearsal` milestone (and its dependent `Customer Go-Live`); the
  SharePoint change-freeze calendar; Outlook June 22 left free; one open GitHub issue titled
  *"Change request: move the launch rehearsal"* (the receiver's target ticket).
- Two browser profiles (Robin / Alex), windows pre-opened: Outlook month view, the GitHub
  milestone page, the change-request issue.

## Scene 1 — The problem (0:00–0:25)

| Screen | Narration |
| --- | --- |
| Teams chat; quick cuts of four panes: the GitHub milestone, the Outlook calendar, Planner tasks, a Teams announcement | "One sentence in chat — 'move the rehearsal a week out' — touches four systems. It's easy to half-do: one updated, three left stale. The usual fix is one more approval queue: it slows everyone, and the approver still decides blind." |

## Scene 2 — Routine work: zero added approval (0:25–1:10)

| Screen | Narration |
| --- | --- |
| Robin, in Copilot Chat with the AI Change Court agent, types: **"post the Project X weekly report"** | "AI Change Court takes the opposite bet. Every request gets the same automatic cross-system analysis —" |
| The agent's reply: low risk, *"Approval required: none — your confirmation executes it"*. Cut to the card: the bold line **"Approval required: none — the requester's confirmation executes it."** above the **Send for approval** / **Give up** buttons | "— and almost none gets an extra approver. This weekly report is my own authority. The card says so, explicitly: approval required — none." |
| Robin clicks **Send for approval** → it executes immediately; the weekly report lands in the Teams channel; the result card shows the outcome | "My confirmation alone executes it. No queue, no waiting — and the evidence and audit record are exactly as complete as for the riskiest change." |

## Scene 3 — The exception: informed approval (1:10–3:10)

| Screen | Narration |
| --- | --- |
| Quick cut: the Outlook month view — **June 22 is empty** | "Now the dangerous one. June 22 is free on the calendar. A human would approve this on sight." |
| Robin: **"move the launch rehearsal to 2026-06-22"** → the agent replies: refused as posed, high risk, three decisive findings — past the contractual launch-readiness SLA (clause LR-3, 2026-06-21 — CRM), inside the release-freeze window (2026-06-19→24 — SharePoint), compresses the `Customer Go-Live` buffer (GitHub) — and proposes **2026-06-18**, with the *View full pipeline & audit* link | "The court reads what no single screen shows: the date is past a contractual readiness cut-off, inside a published release freeze, and it compresses the go-live buffer. Any one is a yellow flag — together, a hard breach. So it refuses the request as posed, and proposes the latest date that honors every constraint." |
| The card: **"⛔ REJECTED as requested — proposing a safer alternative"**, the safe alternative for 06-18, and **"Approvers required (any): eng_lead, comms, account_owner"**. Robin types a note and clicks **Send for approval** | "This is the exception path — and notice *who* it convenes. Each approver was pulled in by a specific piece of evidence: the milestone move names the engineering lead; the contractual risk names the account owner. Not a committee — the owners of this risk." |
| **Cut to Alex's Teams**: the activity-feed notification, then the decision card in the bot chat — the evidence chain, the safer alternative, Robin's note, a note field, **Approve** / **Reject** | "The approver gets the decision where they work — in Teams. And separation of duties is enforced, not assumed: Robin cannot approve Robin's own request; the engine checks the identity, every time." |
| Alex adds a note and clicks **Approve** → the result card; quick cuts: the GitHub milestone now due **2026-06-18** (a real write), the Teams announcement updated | "Alex approves the *safer* plan — informed by the evidence chain, not a hunch. And the execution is real: the milestone, the calendar, the announcement — moved together, or not at all." |
| Open the run page from the signed link: the stage rail (intake → … → audit), per-step before/after, rollback hints, the audit id | "Every run leaves this: the full pipeline, before-and-after snapshots, advisory rollback hints, an append-only audit record." |

## Scene 4 — It fits the process you already have (3:10–4:15)

| Screen | Narration |
| --- | --- |
| Robin: **"What would break if we moved the rehearsal to June 22? Don't change anything."** → the agent runs the analysis-only mode: the same evidence, the risk, the would-be approvers — and states that **nothing was executed** (status: analyzed) | "Maybe your changes already flow through a ticket. Then use the court as a pre-ticket impact check: same analysis, same evidence, the approvers it *would* convene — and a guarantee that nothing ran." |
| Cut to the GitHub issue *"Change request: move the launch rehearsal"*: a comment appeared the moment Robin sent the change for approval — the full evidence packet (risk factors with citations, impact evidence, the safer plan, the run-page link) | "Or keep your ticket as the system of record, and let the court push its evidence into it. The approval you already have just became an informed one. The court doesn't add a second approval board — it supplies the analysis your board was missing." |

## Scene 5 — Close (4:15–5:00)

| Screen | Narration |
| --- | --- |
| The run page / audit record; one simple diagram: M365 Copilot declarative agent → OAuth2-protected MCP → the LangGraph court → pluggable adapters (real or mock per system) | "Under the hood: a declarative agent in Microsoft 365 Copilot, an OAuth2-protected MCP server, one inspectable pipeline, and pluggable adapters per system. Approval policy is data, not code — your rules, your roles." |
| Closing card: the three outcomes | "Fewer half-done changes. Latent breaches refused — with a safer option already on the table. And the rare approver starts from evidence, while the routine majority never waits on anyone. That's AI Change Court." |

## Notes

- **Live vs. mock.** In this recording GitHub, Outlook, SharePoint, and Teams run against real
  services; CRM, Planner, and Entra answer from their mocks (every system has one). The narration
  above never claims more than that.
- **Fallback.** If the tenant is unavailable on recording day, the same script runs tenant-free on
  the [Playground bot](../../m365/playground-bot/): the user switcher plays Robin and Alex, and the
  run page works unchanged. The Copilot Chat panes become bot-chat panes; everything else holds.
