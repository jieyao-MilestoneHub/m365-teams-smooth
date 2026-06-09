# Demo coverage — which trial exercises which system

Which integration each trial reads (**R**) and writes (**W**), derived from
`backend/app/agent/gatherers.py` (reads) and `backend/app/agent/planners.py` (writes). With
`dry_run_default=false`, writes to the real **GitHub**, **Outlook**, and **SharePoint** adapters apply
for real (a milestone PATCH; a calendar event / unsent draft; a folder-permission invite). A real
**Teams** write (`teams:real`) sends a genuine Graph **activity-feed notification** — a real channel
post/read is a *protected* Graph API and is out of scope. **Planner/CRM/Entra** stay in-memory mocks.
Under dry-run every `W` is a *predicted* effect.

| Trial | GitHub | Outlook | SharePoint | Planner | Teams | CRM | Entra |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Reschedule** (launch slip) | R W | R W | — | R W | R W | — | — |
| **Meeting Actions** | — | R W | — | W | R | — | — |
| **Weekly Report** | R | R | — | R | W | — | — |
| Customer Promise | R W | R W | — | — | W | R W | — |
| Vendor Access | — | — | R W | — | — | — | W |

## The recording — the Informed Approval scenario

The headline demo is the single **Reschedule** scenario ([recording-runbook.md](recording-runbook.md)):
one request that rips across four systems, refused-and-proposed-safer, then approved on a full
evidence package. Its real-write systems are **GitHub** (milestone) and **Outlook** (the moved event;
the Board-review conflict it reads):

| Scenario | Shows | Real systems exercised |
| --- | --- | --- |
| **Reschedule** (`move the rehearsal to 2026-06-16`) | impact across four systems; refuse-and-propose-safer; informed approval; audit | **GitHub** (milestone) · **Outlook** (event + Board-review conflict) |

If the audience wants to see the other integrations, two optional add-ons cover the rest:

| Add-on | Shows | Real systems exercised |
| --- | --- | --- |
| **Vendor Access** (over-broad ProjectX access) | least-privilege + expiry + auto-revoke | **SharePoint** (CustomerData folder) |
| **Weekly Report** (`post the Project X weekly report`) | cross-system aggregation into one post | **GitHub** (closed issues) · **Outlook** (events) |

To run any of these against real Microsoft Graph (not mock), use the one-shot
[setup-demo](../deploy/setup-demo.md) (`make setup-demo`) and the per-system setup:
[GitHub](../deploy/github.md) · [Outlook](../deploy/outlook.md) · [SharePoint](../deploy/sharepoint.md),
then set `INTEGRATION_MODE=github:real,outlook:real,sharepoint:real`.
