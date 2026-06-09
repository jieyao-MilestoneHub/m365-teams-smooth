# The demo — Informed Approval

*One request. Four systems. No blind approval.* Approval is common; **informed** approval is rare.
This single scenario shows the difference end to end, and it runs **credential-free** on a laptop.

## The scenario

A program manager types one sentence in Teams — **"move the rehearsal to 2026-06-16"** — and to
them it's just changing a date. The court treats it as the cross-system change it really is, in
three beats:

1. **Impact before approval.** It reads the load-bearing date across four systems: the **GitHub**
   `Launch Rehearsal` milestone, the **Outlook** calendar, dependent **Planner** tasks, and the
   **Teams** announcement. Risk: **HIGH**, with an `eng_lead` + `comms` quorum.
2. **Safety before execution.** 2026-06-16 collides with a real **Board review**, so the court
   **refuses the request as posed** and proposes the next free day, **2026-06-17**, as a safe
   alternative — no plain "approve" is offered. The requester can propose it but cannot self-approve;
   an *informed* approver — seeing the impact, the alternative, and the rollback hints — decides, and
   the run resumes from its durable checkpoint to execute.
3. **Audit after action.** An append-only record of evidence, approvers, verdict, before/after
   snapshots, and rollback hints.

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

Type `move the rehearsal to 2026-06-16` into the Playground chat, watch the Change Court card
render, and click the verdict buttons (`queue` lists pending approvals). With `RUN_LINK_SECRET` set,
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

> The same engine also handles additional capabilities that stay wired and tested — *Meeting Actions*
> (standup follow-ups become owned, dated tasks) and *Weekly Report* (cross-system activity
> aggregated into one channel post). They are not part of the headline demo.
