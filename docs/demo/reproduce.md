# Reproducing the demo screens — fastest path first

Everything below runs **credential-free** on a laptop: the integrations are mocked
(`FORCE_ALL_MOCK` or the default mock selection), the LLM falls back to the deterministic parser,
and dry-run is the default. No Microsoft 365 tenant is required until the last section.

Prerequisites once: Python 3.11+ with [`uv`](https://docs.astral.sh/uv/), Node (for the
Playground), and `cd backend && uv sync` (or `make sync`).

## The demo requests

The headline is the **Informed Approval** scenario — request 1 (the refused reschedule and its safe
alternative); see [recording-runbook.md](recording-runbook.md). Requests 3–4 are additional
capabilities of the same engine, useful for showing breadth locally:

| # | Request | Expected outcome |
| --- | --- | --- |
| 1 | `move the rehearsal to 2026-06-16` | **Headline.** Refused as posed (date conflict) → safe alternative: the next free day; HIGH risk, two-role quorum |
| 2 | `move the rehearsal to 2026-06-17` | The feasible variant (no conflict) — same four-system ripple, HIGH risk |
| 3 | `create action items from standup` | Three owned, dated tasks + a review event; LOW risk, requester authority |
| 4 | `post the Project X weekly report` | One channel post composed from the week's activity; LOW risk |

## 1. Terminal — `make demo`

Runs all four trials end to end and prints each Change Court (evidence, plan or safe alternative,
approvers, verdict, audit id). The order leads with the refusal — the court saying "no, but
here's the safe way" is the moment to show first.

```bash
make demo
```

## 2. Static cards — `make cards`

Exports the Change Court Adaptive Card JSON for the same four trials (court + result cards) to
[`m365/adaptive-cards/generated/`](../../m365/adaptive-cards/generated):

```bash
make cards
```

Open any file in the [Adaptive Cards Designer](https://adaptivecards.io/designer) for a
pixel-faithful, tenant-free card preview — useful for screenshots.

## 3. Clickable cards — `make bot` + the Agents Playground

The [Playground bot](../../m365/playground-bot/) renders the real cards and makes the verdict
buttons live, with no tenant:

```bash
make bot                                          # terminal 1 — bot + backend in-process
npx @microsoft/teams-app-test-tool@latest start   # terminal 2 — opens the Playground UI
```

Type any request from the table above into the Playground chat, watch the Change Court card
render, and click the verdict buttons. `queue` lists pending approvals. For the full
requester-vs-approver flow (the Playground's user switcher plays both people), follow
[two-user-demo.md](two-user-demo.md) — start the bot with an `APPROVER_DIRECTORY` as described
there. Capture notes for screenshots/recordings are in the
[bot's README](../../m365/playground-bot/README.md).

## 4. Second screen — the pipeline run page

With `RUN_LINK_SECRET` set (any 32+ random bytes), every Change Court card carries a
**View pipeline run** link to a read-only, signed run log (`/runs/<thread_id>?t=…`): the stage
rail advances live, the verdict gate shows quorum progress, and execution fills in per-step
before→after results. It inspects — decisions still happen only on the card
([ADR-0011](../reference/adr/0011-read-only-pipeline-run-page.md)).

## Verify before showing anyone

```bash
scripts/verify.sh   # the pre-demo gate: trials + safety + MCP + quality (tenant checks PENDING)
```

## Real tenant (optional)

To run the same trials inside Copilot Chat / Teams: deploy with the
[Container Apps → Teams runbook](../deploy/runbook.md), then walk
[demo-day-checklist.md](demo-day-checklist.md) in order — it exists because the deployed
environment is ephemeral and the prep order matters. Real GitHub evidence (instead of the mock) is
an opt-in: point `INTEGRATION_MODE=github:real` + `GITHUB_TOKEN`/`GITHUB_REPO` at a throwaway repo
(see the [config reference](../integrate/config-reference.md)).
