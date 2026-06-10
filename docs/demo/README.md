# The demo — Informed Approval

*One request. Four systems. No blind approval.* Approval is common; **informed** approval is rare.
This single scenario shows the difference end to end, and it runs **credential-free** on a laptop.

## The scenario

A program manager types one sentence in Teams — **"move the launch rehearsal to 2026-06-22"** — and
to them it's just changing a date. The 22nd is even **free on the calendar**. A human would approve
it on sight. The court refuses it, because it reads what no single screen shows, in three beats:

1. **Impact before approval.** It reads the load-bearing date across systems: the **GitHub**
   `Launch Rehearsal` milestone (and its **dependent** `Customer Go-Live` milestone), the **Outlook**
   calendar, dependent **Planner** tasks, the **Teams** announcement, the **CRM** contract terms, and
   the published **SharePoint** change-freeze calendar.
2. **Safety before execution — the catch no human makes.** The 22nd is clear on the calendar, yet
   cross-referencing three systems reveals a latent breach: it is **past the contractual
   launch-readiness SLA** (clause LR-3, 2026-06-21 — CRM), **inside the release-freeze window**
   (2026-06-19→24 — SharePoint), and it **compresses the `Customer Go-Live` buffer** (GitHub). Any
   one is a yellow flag; together they are a hard breach. The court surfaces the **counterfactual**
   ("had this been approved it would have breached … first breach date 2026-06-22"), **refuses the
   request as posed**, and proposes the latest date that honors every constraint — **2026-06-18** —
   as a safe alternative. No plain "approve" is offered; an *informed* approver (the `eng_lead`,
   `comms`, and `account_owner` quorum), seeing the chain of reasoning, the alternative, and the
   rollback hints, decides, and the run resumes from its durable checkpoint to execute.
3. **Audit after action.** An append-only record of evidence, approvers, verdict, before/after
   snapshots, and rollback hints.

The same machinery handles the simpler cases the same way: **"move the rehearsal to 2026-06-16"**
collides visibly with a **Board review** and is refused for the next free day (**2026-06-17**), while
a clean **2026-06-17** request is approved as feasible.

One more moment worth showing: appending **"and delete the repo"** is **blocked at intake** — no
registered capability supports it, so it is never planned or executed.

Every step runs through the same surfaces: the **Change Court Adaptive Card** (the decision UI), the
**read-only pipeline run page** on a second screen (signed links, CI-style stage rail), and the
append-only audit at the end.

## Reproduce it (credential-free)

Everything below is mocked, dry-run by default, and needs no Microsoft 365 tenant. Prerequisites:
Python 3.11+ with [`uv`](https://docs.astral.sh/uv/), Node (for the Playground), and
`cd backend && uv sync`.

```bash
make demo     # runs the scenario end to end and prints each Change Court
              # (evidence, safe alternative, approvers, verdict, audit id)
make cards    # exports the Adaptive Card JSON to m365/adaptive-cards/generated/
```

Open any exported card in the [Adaptive Cards Designer](https://adaptivecards.io/designer) for a
pixel-faithful, tenant-free preview.

**Clickable cards with live verdict buttons** — the [Playground bot](../../m365/playground-bot/)
renders the real cards with no tenant:

```bash
make bot                                           # terminal 1 — bot + backend in-process
npx @microsoft/teams-app-test-tool@latest start    # terminal 2 — opens the Playground UI
```

Type `move the launch rehearsal to 2026-06-22` into the Playground chat, watch the Change Court card
render the refusal and its reasoning, and click the verdict buttons (`queue` lists pending
approvals). With `RUN_LINK_SECRET` set,
each card also carries a **View pipeline run** link to the read-only, signed run log
(`/runs/<thread_id>`) — it inspects; decisions still happen only on the card.

Verify before showing anyone:

```bash
scripts/verify.sh   # trials + safety + MCP + quality gates (tenant checks report PENDING)
```

## Grounding in real GitHub (optional)

The reschedule moves a milestone titled `Launch Rehearsal`. To run it against a live repository,
create that milestone in a throwaway repo (any due date) and point the GitHub adapter at it:

```bash
INTEGRATION_MODE=github:real GITHUB_TOKEN=<token> GITHUB_REPO=<owner/name> make demo
```

Every other system stays mocked. To run inside Copilot Chat / Teams, deploy the backend over public
HTTPS with Entra ID OAuth2 and sideload the declarative agent in `m365/` (the codebase and the
[Microsoft 365 service docs](../README.md#microsoft-365--azure-service-reference) cover the steps).

## What else the same engine handles (not recorded — play with it yourself)

Informed Approval is the one scenario this demo records. The same pipeline already handles four more
capabilities, wired and tested but deliberately left as *capabilities the architecture supports* — no
demo is built out for them. Run them with `make demo-all` (or `make cards-all` for their cards), or
type the request into the Playground bot:

- **Meeting Actions** — standup follow-ups become owned, dated Planner tasks ("create action items
  from standup").
- **Weekly Report** — cross-system activity aggregated into one channel post ("post the Project X
  weekly report").
- **Customer Promise** — an unsafe "it's GA by <date>" promise is refused; a private preview with
  gated GA is proposed instead ("promise Customer A that SSO is GA by 2026-06-17").
- **Vendor Access** — an over-broad, undated access request is narrowed to least-privilege,
  time-boxed access with auto-revoke ("give the vendor access to Project X until the campaign is
  done").
