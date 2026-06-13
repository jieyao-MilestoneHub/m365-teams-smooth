# Recording script — Microsoft 365 Copilot Chat walkthrough

The recorded walkthrough drives the headline (the Reschedule scenario) with **Microsoft 365 Copilot
Chat as the primary surface**: the declarative agent runs the cross-system impact analysis, the
read-only run page shows the full evidence chain, the existing change ticket gains the evidence
packet, and the Teams Adaptive Card carries the human approval. This page is the bring-up runbook
plus the scene-by-scene narration; the operational guardrails for the live deployment are in
[demo-day-checklist.md](./demo-day-checklist.md), and the product narrative is in
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
   A `200` health and a `401` on `/mcp/` mean the backend is up and the MCP server is auth-gated as
   expected.

2. **Confirm the agent is in Copilot.** Open Microsoft 365 Copilot Chat in the tenant and look for
   **AI Change Court** in the agent list. If it is missing, upload the built package
   (`m365/build/appPackage.zip`) via the Teams admin centre or the Microsoft 365 Agents Toolkit —
   the package already resolves every manifest value and the OAuth connection, so no rebuild is
   needed. (To rebuild after a config change, see [package the app](../../m365/README.md):
   `make package` with the placeholder env vars set.)

3. **Smoke-test before recording.** In Copilot Chat, send the conversation starter
   `move the rehearsal to 2026-06-16`. The agent should reply with a one-line refusal, the next free
   day, and a **View full pipeline & audit** link. When that round-trips, record.

### Notes that affect what the recording shows

- **Knowledge grounding runs server-side.** In Copilot Chat the agent calls the *deployed* backend,
  which authenticates to Foundry IQ and Azure OpenAI with its managed identity — the governance
  citations appear without any local sign-in. (A local `az login` is only needed when running the
  demo scripts against the real services from a workstation.)
- **Which systems run live.** The deployed backend reads GitHub live; Outlook and SharePoint read
  from fixtures that mirror the seeded real data, so the evidence and narration are identical. To
  read the live Outlook calendar and SharePoint freeze calendar in Copilot too, set the backend's
  `INTEGRATION_MODE` to `github:real,outlook:real,sharepoint:real` (with the `GRAPH_*` credentials)
  and redeploy. CRM and Planner are controlled fixtures for reproducible evidence.
- **Reset between takes.** `make setup-demo-reset` restores the GitHub milestone and ticket, the
  seeded Outlook calendar, and the SharePoint freeze calendar, and clears the ticket's prior
  evidence comments.
- **Tenant-free fallback for the card.** The approval Adaptive Card (Scene 5) can be shown without a
  tenant via the Playground bot (`make bot` + the Agents Playground) if recording the live Teams
  card is impractical.

## The walkthrough (≈ 5 minutes)

In Copilot Chat the declarative agent replies with a short text summary and a run-page link — the
decision UI with approve/reject buttons is the Teams Adaptive Card, shown in Scene 5. Narration is
written to read slowly; leave the rest of the budget for screen actions and pauses.

### Scene 1 — the ticket, in Copilot Chat (0:00–0:30)
*Screen: Microsoft 365 Copilot Chat with the AI Change Court agent; the change ticket (a GitHub
issue) alongside.*

> Every team already has a change process — a ticket like this one. It holds the request, but no
> evidence. In Microsoft 365 Copilot, this is our AI Change Court agent. The ticket stays the system
> of record; the agent supplies the evidence it was missing.

### Scene 2 — ask the agent (0:30–1:30)
*Screen: type into Copilot Chat; the agent's reply.*

> *(type)* "What would moving the launch rehearsal to June twenty-second break? Don't change
> anything yet."
>
> The agent runs an analysis-only check — nothing executes. It comes back high risk: the date is
> free on the calendar, but it is past the contractual SLA, inside the release freeze, and it
> compresses the go-live buffer — grounded in our governance policies from the Foundry IQ knowledge
> base. It refuses the date as posed and proposes June eighteenth instead.

### Scene 3 — the full evidence chain (1:30–2:30)
*Screen: click the agent's **View full pipeline & audit** link → the read-only run page.*

> Here is the full pipeline. Three systems — GitHub, the CRM contract, and the SharePoint freeze
> calendar — each holds one fact; only together are they a breach. No single screen shows this. Each
> risk factor is cited back to the governance knowledge base.

### Scene 4 — the ticket stays the system of record (2:30–3:00)
*Screen: the change ticket (GitHub issue) with the new evidence comments.*

> The same evidence landed back on the ticket automatically — "impact analysis, nothing executed,"
> with the approvers it would concern. Routine work comes back with zero approvers. The ticket stays
> the record; the analysis is what it was missing.

### Scene 5 — the human gate (3:00–4:10)
*Screen: the approver's Change Court Adaptive Card in Teams → Accept alternative → the result card.*

> When the evidence demands it, the change escalates to the right approver — and only them. They see
> the same evidence chain in Teams, with the safer alternative. There is no plain "approve" for an
> unsafe request. They accept the alternative; the plan executes step by step, recorded and
> auditable; and the decision posts back to the same ticket.

### Scene 6 — audit and architecture (4:10–4:55)
*Screen: the append-only audit record → the architecture diagram.*

> Everything ends in an append-only audit. One pipeline, behind a Microsoft 365 Copilot declarative
> agent over MCP and OAuth2, grounded by Foundry IQ. The ticket stays the system of record. AI
> Change Court supplies the evidence packet it was missing.

## Delivery notes

- Put the two memory beats slowest: "three systems, one hidden breach" (Scene 3) and the closing
  line (Scene 6).
- Verbalize dates naturally ("June twenty-second", "June eighteenth"), not as ISO strings.
- Let Scenes 3 and 5 breathe — the screen carries the moment; silence is fine while it loads.
- Do one full silent run immediately before recording; if anything misfires, fix it, re-run the
  bring-up checks, and only then record.
