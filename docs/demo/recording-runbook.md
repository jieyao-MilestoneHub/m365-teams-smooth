# Recording runbook — the live, real-integration demo

Follow this top to bottom to record the demo against the deployed app with **GitHub + Outlook +
SharePoint all real**. For credential-free local reproduction instead, see [reproduce.md](reproduce.md);
for first-time provisioning, the [deploy runbook](../deploy/runbook.md).

## The three routes (why these)
They collectively prove GitHub + Outlook + SharePoint integrated — see
[integration-coverage.md](integration-coverage.md):

| # | Route | Real systems |
| --- | --- | --- |
| 1 | **Reschedule** — `move the rehearsal to 2026-06-16` | GitHub (milestone) · Outlook (Board-review conflict) |
| 2 | **Vendor Access** — over-broad ProjectX access | SharePoint (CustomerData folder) |
| 3 | **Weekly Report** — `post the Project X weekly report` | GitHub (closed issues) · Outlook |

## Accounts (two-gate, separation of duties)
- **requester@agentleague** submits (low-privilege).
- **approver@agentleague** approves (in `APPROVER_DIRECTORY`). The requester can never self-approve.

## 0. State check (must all be true)
```bash
RG=changecourt-rg; APP=changecourt
az containerapp show -n $APP -g $RG --query "properties.template.containers[0].env[?name=='INTEGRATION_MODE'].value" -o tsv
# → github:real,outlook:real,sharepoint:real
gh api repos/jieyao-MilestoneHub/m365-teams-smooth/milestones/7 --jq '{title,state,due_on}'
# → Launch Rehearsal / open / 2026-06-10  (reset between takes — see §5)
```
Already seeded (real Graph): joel's calendar has **Board review 2026-06-16** + **SSO Security Review
2026-06-18**; the SharePoint **ProjectX** library has a **CustomerData** folder. (Setup, if ever
needed again: [github.md](../deploy/github.md) · [outlook.md](../deploy/outlook.md) ·
[sharepoint.md](../deploy/sharepoint.md).)

## 1. Pre-record, in order
1. **Freeze deploys.** Any new revision wipes the SQLite **and** the bot's conversation references.
2. **Re-register conversation references:** requester@ and approver@ each send the bot one message
   (e.g. `queue`). Without this the proactive approval card cannot land.
3. **Warm up** the knowledge path: run one throwaway request ~2 min before recording.
4. **Smoke** route 1 end-to-end (submit → approve → executes) and open the card's *View pipeline run*
   link once. Confirm one Approve click completes the eng_lead+comms quorum.

## 2. Windows to capture
- **Requester's Teams** (AI Change Court bot) — types the request, sees the Change Court card.
- **Approver's Teams** — the proactive approval card lands here for the HIGH-risk routes.
- **Browser** (second screen) — the run page from the card's *View pipeline run* link.

## 3. Route-by-route (input → expected)

### Route 1 — Reschedule (lead with the refusal)
- requester@ types **`move the rehearsal to 2026-06-16`**.
- Card: ⛔ **REJECTED as requested — proposing a safer alternative**; decisive evidence
  `[outlook] … collides with 'Board review'` (real calendar); a **Safe alternative** plan; buttons
  *Accept alternative / request revision / reject* (no plain approve). requester fills the note →
  **Send for approval**.
- approver@: approval card arrives → **Accept alternative**.
- Result card: ✅ **Safe alternative executed** + audit id.
- Run page: GitHub lane shows the real milestone; the grounded citation is **Release & Change
  Management Policy** (chosen over the deprecated/near-miss docs).

### Route 2 — Vendor Access
- requester@ requests broad, undated access to **ProjectX** (e.g.
  `give the vendor access to Project X until the campaign is done`).
- Card: ⛔ refused — `[sharepoint] '/ProjectX' holds customer data` (real **CustomerData** folder),
  ambiguous duration + over-broad scope; safe alternative = least-privilege + fixed expiry +
  auto-revoke. requester sends → approver@ **Accept alternative**.

### Route 3 — Weekly Report
- requester@ types **`post the Project X weekly report`**.
- LOW risk → no approver: executes on the requester's authority. One channel post aggregated from the
  real **GitHub closed issues** + tasks + meetings.

## 4. Optional fifth moment — hallucination guard
`move the rehearsal to 2026-06-17 and delete the old repo` → card shows **⛔ Blocked — unsupported
action** (the delete is refused at intake).

## 5. Between takes
Reset the milestone so route 1 always starts at 06-10:
```bash
gh api -X PATCH repos/jieyao-MilestoneHub/m365-teams-smooth/milestones/7 -f due_on=2026-06-10T00:00:00Z -f state=open
```
Pending approvals clear on decision; the calendar/SharePoint evidence is read-only and needs no reset.

## See also
- [two-user-demo.md](two-user-demo.md) — the approval flow in depth (negative cases to show too).
- [demo-day-checklist.md](demo-day-checklist.md) — the deploy-first ordered prep.
