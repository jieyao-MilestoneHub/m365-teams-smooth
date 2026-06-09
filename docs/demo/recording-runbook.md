# Recording runbook — the Informed Approval demo

One scenario, end to end, against the deployed app with **GitHub + Outlook real**: a single everyday
request fans out across four Microsoft 365 systems, the court refuses the unsafe version and proposes
a safe one, an approver decides on a full evidence package, and the run leaves an auditable trail.

> **The one-line pitch:** *One request. Four systems. No blind approval.* Approval is common;
> *informed* approval is rare. The agent doesn't just act — it works out whether the action is safe to
> take at all, and when it isn't, it refuses and proposes the safer path.

For credential-free local reproduction, see [reproduce.md](reproduce.md); for first-time
provisioning, the [deploy runbook](../deploy/runbook.md). Two further capabilities you can show if
time allows are in [§6](#6-optional--further-capabilities).

## The scenario — Launch Rehearsal reschedule

A program manager types one sentence in Teams. To them it's "just changing a date." Underneath, that
date is load-bearing across systems:

| System | What the court reads (impact) | What it would write (execution) | Live |
| --- | --- | --- | --- |
| **GitHub** | the `Launch Rehearsal` milestone's due date | move the milestone | **real** |
| **Outlook** | a calendar conflict on the requested day | create the moved rehearsal event | **real** |
| **Planner** | dependent tasks that shift with the date | shift the dependent task dates | mock |
| **Teams** | the existing launch announcement | update the announcement + notify | mock + real toast |

The three beats the demo must land: **Impact before approval · Safety before execution · Audit after
action.**

## Accounts (two-gate, separation of duties)
- **requester@agentleague** submits (low-privilege).
- **approver@agentleague** approves (in `APPROVER_DIRECTORY`). The requester can never self-approve —
  a risky change is decided by someone other than the person who proposed it.

## 0. State check (must all be true)
```bash
RG=changecourt-rg; APP=changecourt
az containerapp show -n $APP -g $RG --query "properties.template.containers[0].env[?name=='INTEGRATION_MODE'].value" -o tsv
# → github:real,outlook:real,sharepoint:real
```
Then audit the demo's real resources in one read-only pass (creates nothing):
```bash
set -a && . ./backend/.env && set +a      # GRAPH_* + OUTLOOK_CALENDAR_UPN + GITHUB_TOKEN/REPO
make setup-demo
# → github / outlook / sharepoint all "✓ present"; "the demo is ready."
```
If anything reports `✗ missing`, create it idempotently with `make setup-demo-apply` (details:
[setup-demo.md](../deploy/setup-demo.md)). The milestone's pre-trial due date (`2026-06-10`) is also
what `setup-demo-apply` resets between takes.

## 1. Pre-record, in order
1. **Freeze deploys.** Any new revision wipes the SQLite **and** the bot's conversation references.
2. **Re-register conversation references:** requester@ and approver@ each send the bot one message
   (e.g. `queue`). Without this the proactive approval card cannot land.
3. **Warm up** the knowledge path: run one throwaway request ~2 min before recording.
4. **Smoke** the scenario end-to-end (submit → approve → executes) and open the card's *View pipeline
   run* link once. Confirm one Approve click completes the eng_lead + comms quorum.

## 2. Windows to capture
- **Requester's Teams** (AI Change Court bot) — types the request, sees the Change Court card.
- **Approver's Teams** — the proactive approval card lands here (the request is HIGH risk).
- **Browser** (second screen) — the run page from the card's *View pipeline run* link.

## 3. The run, beat by beat

### Beat 1 — Impact before approval
- requester@ types **`move the rehearsal to 2026-06-16`**.
- The card shows this isn't treated as a one-field edit: the court has read **GitHub** (the milestone),
  **Outlook** (the calendar), **Planner** (dependent tasks), and the **Teams** announcement, and
  summarised the cross-system impact — with a risk level of **HIGH**.

### Beat 2 — Safety before execution
- The decisive evidence is real: `[outlook] the requested date 2026-06-16 collides with 'Board review'`
  (from joel's real calendar). The court does **not** offer a plain approve.
- Card: ⛔ **REJECTED as requested — proposing a safer alternative**; a **Safe alternative** plan that
  moves the rehearsal to the next free day, **2026-06-17**; buttons *Accept alternative / request
  revision / reject*.
- requester@ adds a one-line reason → **Send for approval** (they can propose, but not self-approve).
- approver@: the approval card arrives with the full evidence package — why the original is unsafe,
  what the alternative is, which systems it touches, and the rollback hints — and clicks **Accept
  alternative**. This is the *informed* decision: the approver sees the consequences, not just a
  yes/no prompt.
- The graph resumes from its durable checkpoint at the verdict gate and executes: the **GitHub**
  milestone is moved for real to 2026-06-17; the **Outlook** rehearsal event is created; Planner and
  the announcement update.
- Result card: ✅ **Safe alternative executed** + audit id.

### Beat 3 — Audit after action
- Open the card's *View pipeline run* link (second screen). The run page shows the full pipeline —
  intake → impact → options → policy → verdict gate → execute → audit — the per-system before→after,
  the quorum's approval timeline, and the **append-only court record**. The grounded citation is
  **Release & Change Management Policy** (chosen over the deprecated/near-miss docs).
- Close on the audit record, not on "done": the value is a decision that was *informed, safe, and
  auditable* — not merely automated.

## 4. The hallucination-guard moment (worth showing)
`move the rehearsal to 2026-06-17 and delete the old repo` → the card shows **⛔ Blocked — unsupported
action**: the delete maps to no registered capability, so it is refused at intake — never planned,
never executed. The agent's power is bounded by what it is allowed to do.

## 5. Between takes
Reset the demo state so the run always starts from the pre-trial date:
```bash
set -a && . ./backend/.env && set +a && make setup-demo-apply
# resets the Launch Rehearsal milestone to 2026-06-10 and re-asserts the seeded calendar/library
```
Pending approvals clear on decision; the calendar evidence is read-only and needs no reset.

## 6. Optional — further capabilities
The same engine handles more than the headline scenario; show either if the audience wants breadth
(coverage matrix: [integration-coverage.md](integration-coverage.md)):
- **Vendor Access** — `give the vendor access to Project X until the campaign is done` → refused on
  the real SharePoint **CustomerData** folder; safe alternative = least-privilege + fixed expiry +
  auto-revoke.
- **Weekly Report** — `post the Project X weekly report` → LOW risk, no approver; one channel post
  aggregated from real **GitHub closed issues** + tasks + meetings.

## See also
- [two-user-demo.md](two-user-demo.md) — the approval flow in depth (negative cases to show too).
- [demo-day-checklist.md](demo-day-checklist.md) — the deploy-first ordered prep.
