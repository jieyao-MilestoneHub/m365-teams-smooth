# Architecture — the standing engineering contract

The system turns a risky team decision into a reviewable, approvable, auditable cross-system
execution — and, when the decision is unsafe, refuses it and proposes a safer alternative. Keep the
layering and SOLID boundaries below intact; they are what make the project extensible and demo-able
at once.

## Shape

```
Microsoft 365 Copilot Chat / Teams
  └─ Declarative Agent (manifest in m365/)        ← required M365 entry
        │ MCP + OAuth2
        ▼
  FastAPI process (backend/)
     ├─ mcp/        MCP server: tools + resources + OAuth2 resource server (primary surface)
     ├─ api/        minimal REST: health + the read-only run page (signed links; no business logic)
     ├─ bot/        Bot Framework endpoint (/api/messages): the Change Court card's buttons
     ├─ services/   single business layer (MCP, REST, and the bot all delegate here — no duplication)
     ├─ agent/      LangGraph court: intake → impact → options → policy+quorum → [verdict] → execute → verify → audit
     ├─ ports/      abstract interfaces (DIP boundary, incl. the court-runner port)
     ├─ adapters/   integrations (real + mock), persistence, llm providers, knowledge, guardrail, parsers, notifiers
     ├─ presentation/  cross-surface decision-UI rendering (the Adaptive Card builders)
     ├─ llm/        provider-agnostic LLM wire utilities (strict JSON-Schema rendering, untrusted fencing)
     ├─ observability/  structured logging, metrics, request-id propagation, PII redaction
     ├─ security/   HMAC signing for run-page deep links
     └─ domain/     pure models/enums/errors (no framework or SDK imports)
  Teams Adaptive Card = the decision UI (Change Court card). The one web surface is the
  read-only pipeline run page (/runs/{thread_id}, HMAC-signed deep links — ADR-0011):
  it inspects a trial's run, never decides. No dashboard beyond it.
  SQLite (local) → Postgres (later), DB_URL-driven
```

## Non-negotiable boundaries

- **Dependency Inversion:** `agent/` and `services/` depend on `ports/` only — never on the GitHub
  SDK, SQLAlchemy, or an LLM client directly. Concrete implementations live in `adapters/`.
- **One business layer:** MCP tools, REST routers, and the bot handler are thin façades over
  `services/`. No business logic in routers, tools, or turns. The Adaptive Card renders data the
  services produce.
- **Pure domain:** `domain/` imports nothing from FastAPI, LangGraph, or any adapter.

### Why each level exists (read this before adding a file)

Every top-level package answers one question; a new file goes where its *importers* say it
belongs, not where it was first needed:

- `domain/` — what the business talks about (one concept per file, zero framework imports).
- `ports/` — the contracts `agent/` and `services/` are allowed to see (incl. `ports/runner.py`,
  the court-runner port the business layer drives the graph through).
- `adapters/` — one subfolder per technology seam (integrations, persistence, llm providers,
  knowledge, guardrail, parsers, notifiers); real/mock pairs; no loose files at the root.
- `agent/` — root files are graph infrastructure (state/graph/runner/instrument) and the
  deterministic behavior libraries (gatherers/planners/deliberate); `nodes/` is the state machine;
  `agentic/` wraps the libraries with LLM reasoning (every wrapper has a deterministic sibling and
  falls back to it); `policy_rules/` is policy as data.
- `services/` — the single business layer; `mcp/ api/ bot/` are its thin façades.
- `presentation/` — rendering shared by several surfaces (the card builders); a module used by
  bot, notifiers, and tooling must not live inside one surface's folder.
- `llm/` — provider-agnostic wire utilities shared by `agent/` and `adapters/`; distinct from
  `adapters/llm/`, the concrete providers.
- `observability/`, `security/` — cross-cutting single implementations (deliberately not ports).
- Root: `config.py` (env), `container.py` + `asgi.py` (the only composition roots), `main.py`
  (REST-only factory).

**Sanctioned exception:** `adapters/persistence/checkpointer.py` imports LangGraph — it *is* the
graph-saver adapter, so the SDK belongs there. The condition: only the composition root wires it,
and nothing in `agent/` imports the checkpointer directly.

**Size watch:** `services/court_service.py` is large but single-responsibility; split it into a
package only if it grows past ~1000 lines or gains a second concern.

## LangGraph single-agent "Change Court"

A single, inspectable graph, presented as courtroom roles (Prosecutor = impact, Defender = options,
Clerk = audit, Executor = execute). It is one agent today; the multi-agent path is a seam, not a
rewrite (see below).

- **State** (serializable, checkpointed): `thread_id, change_id, raw_request, source, requester,
  run_mode, change, impact, options, risk, quorum, verdict, selected_plan, results, verifications,
  deliberations, audit_id, status, errors`.
- **Nodes** (single responsibility each):
  - `intake` — parse the request into a structured `Change`; **validate every requested action
    against registered adapter capabilities** (hallucination guard — unsupported actions are blocked,
    not planned).
  - `impact` (Prosecutor) — gather second-order consequences via adapter **read** capabilities
    (blockers, customer commitments, renewal value, schedule conflicts) → `ImpactEvidence`.
  - `options` (Defender) — produce a feasible `ExecutionPlan`; when the request is unsafe, produce a
    **safe alternative** (e.g. private preview instead of GA; least-privilege + expiry instead of
    broad access).
  - `policy` (one node covering policy + quorum) — deterministic risk scoring →
    `requires_approval`; derive the **required approvers** (quorum) from impact tags and the
    available **verdict options**. Rules are data, not code.
  - `execute` (Executor) — registry → adapter per step; honors `run_mode` (DRY_RUN returns predicted
    effects, no side effects).
  - `verify` — check the live writes against the reviewed plan (agentic when an LLM is configured);
    findings land in `verifications`.
  - `audit` (Clerk) — append-only before/after snapshot + rollback hints + the full trial record
    (impact, options, approvers, verdict).
- **Verdict = durable interrupt:** suspend at `interrupt()` / `interrupt_before=["execute"]`,
  checkpointed by `thread_id`. The submitting request returns immediately; a later `cast_verdict`
  call rehydrates from the checkpointer and resumes. **Never hold the graph in memory across the
  verdict gap.** Casting the same verdict twice is idempotent — no double execution.
- **Dry-run** is a first-class state field, not a separate code path.

## SOLID integration adapters

- Port `IntegrationAdapter`: `capabilities() / validate() / read(query) / execute(step, mode) /
  fetch_before() / suggest_rollback()`. Capabilities are typed and split into **read** (evidence for
  the impact node) and **write** (actions for execution).
- `BaseIntegrationAdapter` template-methods the dry-run branch and error→`IntegrationError` mapping.
- `IntegrationRegistry` selects **real vs mock per system from config** (`integration_mode`, plus a
  `FORCE_ALL_MOCK` flag to run with zero external credentials).
- **Open/Closed:** a new integration = one adapter module + one registration. No edits to graph,
  services, REST, or MCP.
- **Scope discipline:** only the adapters the headline demo (Informed Approval) and the additional
  capabilities the engine already handles require are built. All seven systems have mocks; real
  adapters exist for GitHub and — behind `GRAPH_*` credentials — Outlook, SharePoint, and Teams;
  Planner, CRM, and Entra are mock-only. Others (ServiceNow, a generic Graph adapter) are backlog.

## LLM provider & guardrail

- Port `LLMProvider`: `complete()` for free text plus `generate(LlmRequest) → LlmResult`. The
  request carries provider-agnostic intent — `cacheable_prefix` (stable system text),
  `system_suffix` (volatile system text), a plain-JSON `json_schema`, a per-call `max_tokens`, an
  optional per-call `model`/deployment override (the composition root maps the lightweight call
  sites — the parser, the deliberation trace — onto `AZURE_OPENAI_DEPLOYMENT_FAST` when set) — and
  the result returns the text plus per-call telemetry (`input_tokens`, `output_tokens`,
  `cached_prefix_tokens`, provider `request_id`). No SDK types cross the port; offline fakes and
  stubs implement only `complete()` and the default `generate()` keeps working.
- **Structured output is native and strict.** Wire models render through
  `app/llm/structured.py: schema_of()` into the cross-provider strict schema subset (every
  property required, `additionalProperties: false`, no defaults; free-form dicts travel as
  JSON-encoded strings, decoded by a model validator). The Azure adapter sends it as a strict
  `response_format`; a truncated (`finish_reason=length`) or refused structured reply raises a
  typed `LlmOutputError`. Every LLM call site keeps a deterministic fallback, and client-side
  Pydantic validation stays regardless of the provider guarantee.
- **Prompt caching is layout, not API.** The cacheable prefix leads as its own system message and
  every volatile part (the Defender's stance, the parser's date line) comes after it, matching the
  service's automatic exact-prefix caching; cache hits surface via `cached_prefix_tokens`.
- **The SDK is the single retry owner** (`LLM_MAX_RETRIES`; exponential backoff, honors
  retry-after) — never add an outer retry wrapper around LLM calls. Failures classify into
  `llm.errors.{rate_limited, timeout, connection, server, invalid_request}`; each call emits one
  `llm.call` log line plus `llm.calls` / `llm.tokens.{input,output,cached}` counters.
- Port `GuardrailPort` screens untrusted input (the raw request, gathered evidence) **before** any
  LLM reasons over it — Azure Prompt Shields when `CONTENT_SAFETY_ENDPOINT` is set, an offline
  heuristic otherwise; flagged input falls back to the deterministic path. Third-party content is
  fenced in `<untrusted_data>` blocks (`app/llm/untrusted.py`). Screening never raises.
- Portability seams for a second platform adapter (credential providers rather than static keys,
  logical-model → platform-ID mapping, normalized throttling, capability flags) and the
  deliberately deferred hardening (circuit breaker, streaming, batch APIs) are recorded in
  **ADR-0013**.

## Persistence

- SQLAlchemy + Alembic, `DB_URL`-driven (SQLite local, Postgres later).
- Audit records are **append-only** — never updated. Rollback hints are advisory data, not
  auto-executed.
- LangGraph checkpoints behind a `CheckpointStore` port so the saver is swappable.

## Extensibility seams (do not paint over)

- **Connected/multi-agent:** nodes are state-in/state-out; the courtroom roles (Prosecutor, Defender,
  Clerk, Executor) slot in behind a `SubAgentRegistry` mirroring `IntegrationRegistry`.
- **More MCP tools / Adaptive Cards:** `mcp/tools.py` is a thin façade; card templates are data in
  `m365/adaptive-cards/`.
- **`ApprovalNotifier` port:** approval channels compose behind it without graph changes — the
  Teams activity feed and the proactive bot card today; email/webhook later.

Record significant choices as ADRs under `docs/adr/` (e.g. the verdict-interrupt-vs-MCP-statelessness
decision).
