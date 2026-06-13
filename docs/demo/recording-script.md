# Recording script — Microsoft 365 Copilot Chat walkthrough

The recorded walkthrough drives the headline (the Reschedule scenario) in four scenes, with
**Microsoft 365 Copilot Chat as the primary surface**: the declarative agent runs the cross-system
impact analysis, the read-only run page shows the evidence chain, the existing change ticket gains
the evidence packet, and the Teams Adaptive Card carries the human approval. This page is the
bring-up checks plus the scene-by-scene script; the operational guardrails for the live deployment
are in [demo-day-checklist.md](./demo-day-checklist.md), and the product narrative is in
[README.md](./README.md).

## Bring up the Copilot surface

The agent calls the deployed backend's MCP server over OAuth2, so the walkthrough needs the backend
reachable over public HTTPS and the declarative agent available in the tenant's Copilot.

1. **Confirm the backend is reachable.** Get `<public-base-url>` from `terraform output
   public_base_url`, the `resource` field of the manifest inside `m365/build/appPackage.zip`, or the
   Container App in the Azure portal, then:
   ```bash
   curl -s https://<public-base-url>/api/health      # → {"status":"healthy",...}
   curl -s -o /dev/null -w "%{http_code}\n" https://<public-base-url>/mcp/   # → 401 (OAuth2-protected)
   ```

2. **Confirm the agent is in Copilot.** Open Microsoft 365 Copilot Chat in the tenant and look for
   **AI Change Court** in the agent list. If it is missing or stale, upload the built package
   (`m365/build/appPackage.zip`) via the Teams admin centre or the Microsoft 365 Agents Toolkit — a
   version bump may prompt re-consent. To rebuild after a manifest change, see
   [package the app](../../m365/README.md).

3. **Smoke-test, then reset.** Send the Scene 1 prompt once and confirm the agent renders the
   **View full pipeline & audit** link *with a URL* and that issue #440 gains the
   "Impact analysis — nothing executed" comment. Then run the reset (below) to clear the smoke-test
   comment before recording.

## Before each take — reset the demo data

Run from the repo root in **Git Bash** (the `.env`-loading syntax is POSIX):

```bash
cd backend && set -a && . ./.env && set +a && PYTHONUTF8=1 uv run python -m scripts.setup_demo --apply --force
```

In **PowerShell** that Bash line fails (`set -a` is parsed as `Set-Variable`); from `backend/`, load
`.env` into the session first:

```powershell
cd backend
Get-Content .env | Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object { $n,$v = $_ -split '=',2; [Environment]::SetEnvironmentVariable($n.Trim(), $v.Trim()) }
$env:PYTHONUTF8 = '1'; uv run python -m scripts.setup_demo --apply --force
```

Confirm the setup table shows every demo resource present: the GitHub milestone, ticket #440, the
calendar events, and the SharePoint freeze calendar. The reset restores the seeded read-side and
clears both the seeded calendar and any event a prior take's execution created, so each take starts
identical. (Equivalent make target: `make setup-demo-reset`.)

### Notes that affect what the recording shows

- **Knowledge grounding runs server-side.** In Copilot Chat the agent calls the *deployed* backend,
  which authenticates to Foundry IQ and Azure OpenAI with its managed identity — the governance
  citations appear without any local sign-in. (A local `az login` is only needed when running the
  demo scripts against the real services from a workstation.)
- **Which systems run live.** The deployed backend reads and writes GitHub, Outlook, SharePoint,
  and Teams live, with `DRY_RUN_DEFAULT=false` — so an accepted plan performs real writes (the
  milestone actually moves, the calendar event is actually created). CRM and Planner are controlled
  fixtures for reproducible evidence. Because execution writes for real, run the reset above between
  takes.
- **Scene 3 needs two identities.** The requester submits; a different approver identity decides on
  the Teams card (the requester cannot approve their own request). The card is the bot surface
  (separate from the MCP OAuth), so dry-run Scene 3 once to confirm the approver receives the card.
- **Tenant-free fallback for the card.** The approval Adaptive Card (Scene 3) can be shown without a
  tenant via the Playground bot (`make bot` + the Agents Playground) if recording the live Teams
  card is impractical.

## The walkthrough (≈ 5 minutes)

In Copilot Chat the declarative agent replies with a short text summary and a run-page link — the
decision UI with approve/reject buttons is the Teams Adaptive Card, shown in Scene 3.

### Scene 1 — Copilot asks the right question (0:00–1:20)

**Screen:** Microsoft 365 Copilot Chat with the AI Change Court agent visible. GitHub issue #440 is
open beside it.

**Presenter action:** Type in Copilot:

```text
What would moving the launch rehearsal to June 22nd break? Don't change anything yet.
```

Wait for the agent response: high risk, unsafe date, June 18 alternative, policy reason, and a
**View full pipeline & audit** link.

**Voiceover:**

> Every team already tracks changes somewhere — here, in a ticket.
> The ticket has the request: move the launch rehearsal to June twenty-second.
> But it does not show whether that date is safe.
>
> In Microsoft 365 Copilot, this is our AI Change Court agent.
> We start with a question, not an action.
> Nothing changes. No approval starts.
>
> The agent checks the connected sources and returns high risk.
> June twenty-second looks free on the calendar, but it is past the contract cut-off, inside the
> release freeze, and too close to customer go-live.
>
> So the agent marks the date unsafe, shows the policy reason, and proposes June eighteenth instead.

### Scene 2 — evidence goes back to the ticket (1:20–2:35)

**Screen:** Click **View full pipeline & audit**. Show the run page. Then switch back to GitHub
issue #440.

**Presenter action:**

1. Open the run page.
2. Scroll to the cross-system evidence and the policy basis.
3. Return to GitHub issue #440.
4. Refresh and show the new "Impact analysis — nothing executed" comment.

**Voiceover:**

> Here is the trail behind the answer.
> GitHub shows the milestone dependency.
> The contract evidence shows the cut-off.
> SharePoint shows the freeze calendar.
>
> No single screen shows the whole risk.
> Each fact looks small alone. Together, they make the original date unsafe.
> And every risk factor points back to a policy reason — not just an AI opinion.
>
> The same evidence is added back to the ticket automatically.
> The comment says: analysis only, nothing changed.
> It includes the risk, the evidence, the safer date, and the people this decision would concern.
>
> Routine work is different: low-risk changes come back with zero approvers.

### Scene 3 — Teams becomes the decision surface (2:35–4:10)

**Screen:** Copilot as requester, then Teams as approver. Show the Change Court Adaptive Card and the
result card.

**Presenter action:**

1. In Copilot as requester, type:

   ```text
   Submit the reschedule for approval.
   ```

2. Switch to the approver account in Teams.
3. Open the Change Court card.
4. Click **Accept alternative**.
5. Wait for execution to finish.
6. Show the updated resource links and the decision posted back to ticket #440.

**Voiceover:**

> When a human decision is needed, it appears in Teams.
>
> The approver sees the same evidence, the policy reason, and the safer date.
> For this unsafe request, they are not asked to approve the risky date.
> They can accept the safer date, ask for a revision, or reject it.
>
> The requester cannot approve their own request.
>
> The approver accepts June eighteenth.
> The reviewed plan runs step by step, with links to the resources it updated.
> And the decision is posted back to the same ticket.

### Scene 4 — audit and architecture (4:10–4:55)

**Screen:** The run page audit section, then the architecture diagram.

**Presenter action:** Pause on the append-only audit record, then switch to the architecture diagram.

**Voiceover:**

> Everything ends in an append-only audit record: the request, evidence, policy reason, decision,
> result, and recovery hints.
>
> Under the hood: Microsoft 365 Copilot, Teams, MCP with OAuth2, FastAPI, LangGraph, Microsoft
> Graph, GitHub, and a governance knowledge base.
>
> Copilot is the entry point.
> Teams is the decision surface.
> The ticket remains the main record.
>
> AI Change Court adds the evidence needed to make safer change decisions.

## Delivery notes

- Put the two memory beats slowest: "Together, they make the original date unsafe" (Scene 2) and the
  closing line (Scene 4).
- Verbalize dates naturally ("June twenty-second", "June eighteenth"), not as ISO strings.
- Let Scenes 2 and 3 breathe — the screen carries the moment; silence is fine while it loads.
- Do one full silent run immediately before recording; if anything misfires, fix it, re-run the
  bring-up checks and the reset, and only then record.
