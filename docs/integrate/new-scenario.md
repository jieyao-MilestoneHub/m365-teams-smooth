# Adding a new scenario — rule pack + gatherer + planner

A *scenario* is a kind of decision the court knows how to try: what evidence to gather, what a
feasible plan looks like, when the request is unsafe and what the safer alternative is, and who
must approve. The five shipped scenarios (reschedule, meeting actions, weekly report, customer
promise, vendor access) each consist of exactly three registrations — yours will too.

## The three pieces

### 1. A rule pack — governance as data

`backend/app/agent/policy_rules/packs.py` holds one `RulePack` per scenario family. A pack
declares, as data:

- **match** — which changes it governs: `any_action_capability` (capability names) and/or
  `any_tag` (evidence tags);
- **risk_factors** — evidence tag → additive weight; a factor may set `marks_unsafe: true`, which
  forces the safer-alternative path;
- **risk_bands** — score thresholds for LOW / MEDIUM / HIGH;
- **quorum** — `ApproverRule(role, when_tag)` entries: a role is required only when its tag fired.
  No rule firing means no approver — a LOW-risk change executes on the requester's own
  confirmation;
- **verdict options** — per outcome (default / when unsafe / when high-risk): an unsafe request,
  for example, offers `accept_alternative` instead of a plain approve.

Add your pack and export it from `default_packs()`. The policy node interprets packs generically —
adding a scenario adds **zero** code to it.

### 2. A gatherer — evidence for the Prosecutor

`backend/app/agent/gatherers.py`. A gatherer takes the parsed change, calls **read** capabilities
through the adapter registry, and returns evidence items plus the tags your rule pack keys on.
Register it in the `GATHERERS` dict under your scenario's subject key. The impact node looks the
gatherer up by the change's subject, runs it, and grounds the evidence through the knowledge port
(citations included) — see [foundry-iq.md](foundry-iq.md).

### 3. A planner — the Defender's output

`backend/app/agent/planners.py`. A planner takes the change and the gathered evidence and returns
an `ExecutionPlan` — either the feasible steps (each referencing a registered **write**
capability), or, when the evidence marked the request unsafe, a **safe alternative** that
supersedes it (a conflict-free date, least-privilege access, a narrower scope). Register it in
the `PLANNERS` dict under the same subject key.

## How it flows

Your three pieces slot into the existing pipeline
([View ②](../architecture/02-court-pipeline.html)) without touching it:

```
intake  — parses the request to a subject + requested actions (capability-validated)
impact  — runs YOUR gatherer            → evidence + tags
options — runs YOUR planner             → plan or safe alternative
policy  — interprets YOUR rule pack     → risk, quorum, verdict options
[verdict] → execute → verify → audit    — unchanged
```

## Prerequisites and order of work

1. **Capabilities first.** Every read your gatherer makes and every step your planner emits must
   be a registered capability. If your scenario needs a system the court doesn't know, add the
   adapter first — [third-party-adapter.md](third-party-adapter.md).
2. **Seed the mocks.** Give the mock adapters believable data for your scenario so it runs (and
   demos) credential-free.
3. **Write the golden expectations.** Each scenario records its request, seed data, impact tags,
   risk score, plan shape, and verdict options in
   [reference/trials.md](../reference/trials.md), enforced by the golden-trial tests. Add yours
   there — that table is what keeps the scenario honest as the code evolves.
4. **Optional surfaces.** A conversation starter in the M365 manifest makes the scenario
   discoverable in chat — [mcp-tools-and-agent-manifest.md](mcp-tools-and-agent-manifest.md).

## Design guidance

- **Let the evidence decide safety.** Don't hard-code "this request type is dangerous" — emit a
  tag from the gatherer when the evidence shows the problem, and let the pack's `marks_unsafe`
  factor mark it. That keeps the refusal explainable: the card shows the evidence that triggered
  it.
- **Always offer the safer path.** A bare rejection is the weakest outcome the court can produce.
  If your scenario can be unsafe, decide up front what its safe alternative looks like.
- **Tag vocabulary.** Reuse existing tags (`schedule.*`, `comms.*`, `access.*`, …) where they fit;
  new tags are fine but must be emitted by your gatherer and consumed by your pack consistently —
  see [policy-and-quorum.md](../reference/policy-and-quorum.md) for the current vocabulary.

## See also

- [Policy & quorum](../reference/policy-and-quorum.md) — how packs are interpreted.
- [ADR-0009 — agentic roles and governed autonomy](../reference/adr/0009-agentic-roles-and-governed-autonomy.md)
  — why the gatherer/planner may use the LLM but the pack never does.
- [The demo trials](../reference/trials.md) — five worked examples of exactly this pattern.
