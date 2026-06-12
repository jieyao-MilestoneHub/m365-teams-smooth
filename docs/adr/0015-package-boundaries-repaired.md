# ADR-0015 — Package boundaries repaired: runner port, llm/ and presentation/ packages

## Status

Accepted (2026-06-12).

## Context

An import-graph audit checked the codebase against its documented layering ("`agent/` and
`services/` depend on `ports/` only; `domain/` stays pure; the surfaces are thin façades").
Most boundaries held completely — domain purity, FastAPI/SQLAlchemy/botbuilder isolation, the
single business layer, and composition-root discipline all passed. Three edges did not:

1. `services/court_service.py` imported `agent/runner.CourtRunner` and
   `agent/state.{CourtState, initial_state, serialize}` — the business layer coupled to agent
   internals instead of a contract.
2. `adapters/parsers/llm_backed.py` imported `agent/agentic/{structured, untrusted}` — an adapter
   reaching into the agent for what are in fact provider-agnostic utilities.
3. `mcp/cards.py` was imported by the bot, the notifiers, and the composition root — and by
   nothing inside `mcp/` — cross-surface presentation living inside one surface's folder.

## Decision

1. **Court-runner port.** `app/ports/runner.py` defines `CourtRunnerPort`
   (`start/resume/advance/update/state`) and owns the `CourtState` TypedDict (zero runtime
   dependencies; re-exported from `app.agent.state` for the nodes). `start()` absorbs initial-state
   construction, so callers describe the submitted change and the agent owns its state shape. The service
   depends on the port; the composition root still constructs the concrete `CourtRunner`.
2. **`app/llm/`** — provider-agnostic LLM wire utilities (`structured.py`: strict JSON-Schema
   rendering and reply parsing; `untrusted.py`: third-party content fencing), shared by the agent
   roles and the LLM-backed parser adapter. Distinct from `adapters/llm/`, the concrete providers.
3. **`app/presentation/`** — cross-surface decision-UI rendering (the Adaptive Card builders),
   imported by the bot, the bot-card notifier, the ASGI root, and the export tooling.
4. **Sanctioned exception, recorded:** `adapters/persistence/checkpointer.py` imports LangGraph —
   it is the graph-saver adapter, so the SDK belongs there; only the composition root wires it and
   nothing in `agent/` imports it directly.

## Consequences

- `grep -rn "from app.agent" backend/app/services/ backend/app/adapters/` returns nothing; the
  graph engine is swappable behind a contract like every other dependency.
- The placement rule the tree now follows: **a module lives where its importers say it belongs** —
  shared-by-surfaces code is never inside one surface's folder, and shared-by-layers utilities are
  never inside one layer's internals.
- `services/court_service.py` stays a single module on purpose (large but single-responsibility);
  the watch line is ~1000 lines or a second concern, whichever comes first.
