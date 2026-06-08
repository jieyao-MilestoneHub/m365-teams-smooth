# Demo coverage — which trial exercises which system

Which integration each trial reads (**R**) and writes (**W**), derived from
`backend/app/agent/gatherers.py` (reads) and `backend/app/agent/planners.py` (writes). Writes to the
real **GitHub** adapter apply for real (with `dry_run_default=false`); writes to **Outlook/SharePoint**
stay dry-run only (read-only-real adapters), so their `W` is a *predicted* effect.

| Trial | GitHub | Outlook | SharePoint | Planner | Teams | CRM | Entra |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Reschedule** (launch slip) | R W | R W | — | R W | R W | — | — |
| **Meeting Actions** | — | R W | — | W | R | — | — |
| **Weekly Report** | R | R | — | R | W | — | — |
| Customer Promise | R W | R W | — | — | W | R W | — |
| Vendor Access | — | — | R W | — | — | — | W |

## The recording lineup (GitHub + Outlook + SharePoint)

The three everyday trials never touch SharePoint — only **Vendor Access** does. So the recording uses:

| Route | Shows | Real systems exercised |
| --- | --- | --- |
| 1. **Reschedule** (`move the rehearsal to 2026-06-16`) | refuse-and-propose-safer; one request rippling four systems | **GitHub** (milestone) · **Outlook** (Board-review conflict) |
| 2. **Vendor Access** (over-broad ProjectX access) | least-privilege + expiry + auto-revoke | **SharePoint** (CustomerData folder) |
| 3. **Weekly Report** (`post the Project X weekly report`) | cross-system aggregation into one post | **GitHub** (closed issues) · **Outlook** (events) |

Collectively the three routes cover **GitHub + Outlook + SharePoint** — GitHub and Outlook twice (1 & 3),
SharePoint once (2). To run them against real Microsoft Graph (not mock), see the per-system setup:
[GitHub](../deploy/github.md) · [Outlook](../deploy/outlook.md) · [SharePoint](../deploy/sharepoint.md),
then set `INTEGRATION_MODE=github:real,outlook:real,sharepoint:real`.

> The earlier `move the rehearsal to 2026-06-17` (feasible) and `create action items from standup`
> remain available; the lineup above is the minimal set that demonstrates all three integrations
> working together.
