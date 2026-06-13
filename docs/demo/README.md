# The demo — the ticket stays the system of record

A change-request ticket already exists in the team's normal system of record — a GitHub issue, an
ITSM change, an approval queue. The ticket holds the request; it is missing the impact evidence.
That gap is what this demo fills:

> **The ticket stays the system of record. AI Change Court supplies the evidence packet the
> ticket was missing.**

The court is not a second approval board. It strengthens the existing approval process with
evidence: before anyone approves, an **analysis-only trial** reads the connected systems, gathers
what would break, proposes a safer alternative when the request is unsafe as posed, and works out
which approvers the evidence would actually concern — **nothing executes** — and the packet lands
back on the ticket as a comment. Routine work shows **zero would-be approvers**; high-risk work
names the specific owners its evidence implicates. The whole flow runs **credential-free** on a
laptop.

## Act 1 — the evidence packet (analysis only)

The ticket says: **"move the launch rehearsal to 2026-06-22."** To the requester it's just a date
change — the 22nd is even **free on the calendar**, so the ticket's approver would wave it
through on sight. The analysis-only trial reads what no single screen shows: the **GitHub**
`Launch Rehearsal` milestone (and its dependent `Customer Go-Live`), the **Outlook** calendar,
dependent **Planner** tasks, the **Teams** announcement, the **CRM** contract terms, and the
published **SharePoint** change-freeze calendar. Cross-referencing three of them reveals a latent
breach: the 22nd is **past the contractual launch-readiness SLA** (clause LR-3, 2026-06-21 —
CRM), **inside the release-freeze window** (2026-06-19→24 — SharePoint), and it **compresses the
`Customer Go-Live` buffer** (GitHub).

The packet that lands on the ticket carries the counterfactual ("had this been approved it would
have breached … first breach date 2026-06-22"), the risk factors with citations, a **safer
alternative** — 2026-06-18, the latest date honoring every constraint — and the **would-be
approvers** the evidence implicates: `eng_lead`, `comms`, `account_owner`. Nothing was executed;
no approval round-trip started; the run cannot be resumed into execution.

The same act shows the other pole: a routine request ("create action items from standup") comes
back **low risk, zero would-be approvers** — the analysis says the requester's own confirmation
would carry it. Routine work does not gain an extra approver; high-risk work gets the right ones.

## Act 2 — escalation, when the evidence demands it

If the team lets the court act on what it found, the same change resubmits into the court's own
exception-based gate — and the same webhook keeps the ticket current: an `approval_requested`
comment when the quorum convenes, a `decided` comment with the outcome. No plain "approve" is
offered for an unsafe request; the informed approver adopts the safer alternative, the run
resumes from its durable checkpoint, and execution follows the reviewed plan **step by step** —
failures are recorded, verified, and auditable, never silently half-done. An append-only record
keeps the evidence, approvers, verdict, before/after snapshots, and rollback hints.

The same machinery handles the simpler cases the same way: **"move the rehearsal to 2026-06-16"**
collides visibly with a **Board review** and is refused for the next free day (**2026-06-17**),
while a clean **2026-06-17** request is approved as feasible. Appending **"and delete the repo"**
is **blocked at intake** — no registered capability supports it, so it is never planned or
executed. And an off-script request the rule packs don't govern lands on the ungoverned floor and
waits for a manager.

## Reproduce it (credential-free)

Everything below is mocked, dry-run by default, and needs no Microsoft 365 tenant. GitHub,
Outlook, SharePoint, and Teams can run live when configured; CRM and Planner are controlled
fixtures for reproducible evidence. Prerequisites: Python 3.11+ with
[`uv`](https://docs.astral.sh/uv/), Node (for the Playground), and `cd backend && uv sync`.

```bash
make demo-ticket   # both acts: the analyzed packets, then the escalation —
                   # each packet printed exactly as the ticket comment it becomes
make demo          # the court-side walk of the same scenario (evidence, safe
                   # alternative, approvers, verdict, audit id)
make cards         # exports the Adaptive Card JSON to m365/adaptive-cards/generated/
```

To land the packets on a **real GitHub issue**, run the reference receiver and point the webhook
at it (`make setup-demo-apply` creates the demo ticket and prints its `EVIDENCE_ISSUE` number;
`make setup-demo-reset` reseeds present resources and clears the ticket's prior evidence
comments between takes):

```bash
GITHUB_TOKEN=<token> GITHUB_REPO=<owner/name> EVIDENCE_ISSUE=<number> \
    uv run uvicorn scripts.evidence_receiver:app --port 8088   # from backend/
EVIDENCE_WEBHOOK_URL=http://localhost:8088/evidence make demo-ticket
```

The issue gains four comments: two **"Impact analysis — nothing executed"** packets (the breach
with its would-be approvers, the routine request with none), then **"Approval requested"** and
**"Decision recorded"** from the escalation. Swap the receiver's one GitHub call for any ITSM API
to land the same packets in another system of record.

Open any exported card in the [Adaptive Cards Designer](https://adaptivecards.io/designer) for a
pixel-faithful, tenant-free preview.

**Clickable cards with live approval buttons** — the [Playground bot](../../m365/playground-bot/)
renders the real cards with no tenant:

```bash
make bot                                           # terminal 1 — bot + backend in-process
npx @microsoft/teams-app-test-tool@latest start    # terminal 2 — opens the Playground UI
```

Type `move the launch rehearsal to 2026-06-22` into the Playground chat, watch the Change Court card
render the refusal and its reasoning, and drive the two identity gates with the Playground's user
switcher: send it for approval as the requester, then switch users and decide as the approver
(`queue` lists the approvals waiting on you). With `RUN_LINK_SECRET` set,
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

The ticket flow above is the one scenario this demo records. The same pipeline already handles four
more capabilities, wired and tested but deliberately left as *capabilities the architecture
supports* — no demo is built out for them. Run them with `make demo-all` (or `make cards-all` for
their cards), or type the request into the Playground bot:

- **Meeting Actions** — standup follow-ups become owned, dated Planner tasks ("create action items
  from standup") — low risk, **no approver added**; the requester's confirmation executes it.
- **Weekly Report** — cross-system activity aggregated into one channel post ("post the Project X
  weekly report") — the requester's own authority; **no approver added**.
- **Customer Promise** — an unsafe "it's GA by <date>" promise is refused; a private preview with
  gated GA is proposed instead ("promise Customer A that SSO is GA by 2026-06-17").
- **Vendor Access** — an over-broad, undated access request is narrowed to least-privilege,
  time-boxed access with auto-revoke ("give the vendor access to Project X until the campaign is
  done").
