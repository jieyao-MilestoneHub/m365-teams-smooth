# Integrating a third-party system — one adapter, one registration

Connecting any external system (a ticketing tool, a wiki, a deployment platform, …) means writing
one adapter module and registering it once. The graph, services, MCP, and REST do not change.

## The port you implement

`backend/app/ports/integration.py` defines `IntegrationAdapter` — the single boundary between the
court and any external system:

| Method | Purpose |
| --- | --- |
| `system` | The system key (e.g. `"github"`, `"servicenow"`). |
| `capabilities()` | The read and write capabilities this system registers (see below). |
| `validate(action)` | Raise `CapabilityNotFoundError` when an action is unsupported or its params invalid. |
| `read(query)` | Run a read capability and return raw data — **no side effects**. |
| `execute(step, mode)` | Apply a write step; under `DRY_RUN` return predicted effects only. |
| `fetch_before(step)` | Snapshot current state before a write (for the audit's before/after). |
| `suggest_rollback(step, before)` | Produce an advisory rollback hint (never auto-executed). |

Adapters stay ignorant of the policy tag vocabulary — translating read results into tagged
evidence is the impact node's job, not yours.

## Subclass the template, implement six hooks

In practice you extend `BaseIntegrationAdapter`
(`backend/app/adapters/integrations/base.py`), which already owns the cross-cutting behavior so
every adapter doesn't reimplement it:

- the **DRY_RUN guarantee** — your apply hook is never called in dry-run mode;
- **error mapping** — every SDK exception becomes a typed `IntegrationError`; nothing leaks
  upstream;
- **retries** — idempotency-aware retry classes (liberal for reads and idempotent writes,
  conservative for writes that might have landed).

You implement six hooks: `_capabilities()`, `_read()`, `_predict()` (dry-run effects),
`_apply()` (live effects), `_fetch_before()`, `_rollback()`.

## Declare capabilities — this is the safety contract

Each capability (`backend/app/domain/capability.py`) carries:

- a name, `system.verb_object` — e.g. `github.update_milestone_due`;
- a kind — `READ` (evidence for the impact node) or `WRITE` (actions for execution);
- a `params_schema` — required keys, regex `pattern` constraints, `format: "date"` for ISO dates.

The intake **hallucination guard** validates every requested action against this catalog before
anything is planned: an action your adapter didn't declare — or whose parameters don't match the
schema — is blocked and recorded, never executed. Declare narrowly: schema-constrain identifiers
(e.g. a `safe_repo`-style pattern) so traversal and injection attempts die at the boundary. The
merged catalog is visible at the MCP resource `court://capabilities`.

## Register it (the only core edit)

`backend/app/container.py` builds a candidates map — `{system: {"mock": …, "real": …}}` — and
hands it to `build_registry(settings, candidates)`. Add your system there:

1. Always register a **mock** that returns realistic seeded data (this keeps
   `FORCE_ALL_MOCK=true` runs green and gives the trials deterministic evidence).
2. Register the **real** adapter conditionally on its credentials being configured.
3. Select per system at runtime with `INTEGRATION_MODE` (e.g.
   `INTEGRATION_MODE=github:real,servicenow:mock`); anything unlisted falls back to mock.

## Checklist

- [ ] Adapter module under `backend/app/adapters/integrations/` extending
      `BaseIntegrationAdapter`; six hooks implemented.
- [ ] Mock variant with realistic seed data; real variant gated on config.
- [ ] Capabilities named `system.verb_object`, params schema-constrained.
- [ ] Registered in the container's candidates map — and nowhere else.
- [ ] Unit tests with fakes; real-API tests recorded, not live.
- [ ] `FORCE_ALL_MOCK=true` still runs the full pipeline with zero credentials.
- [ ] One adapter per PR.

## See also

- [ADR-0002 — the integration adapter port](../reference/adr/0002-integration-adapter-port.md)
- [ADR-0007 — dry-run default and live-write gating](../reference/adr/0007-dry-run-default-and-live-write-gating.md)
- [Domain & capability schema](../reference/domain-and-capability-schema.md) — the existing
  capability catalog and naming conventions.
- [new-scenario.md](new-scenario.md) — if your system should also drive a new kind of trial.
- [config-reference.md](config-reference.md) — the integration env vars.
