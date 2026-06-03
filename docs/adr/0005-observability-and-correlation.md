# ADR-0005: Observability and correlation strategy

- **Status:** Accepted
- **Date:** 2026-06-03

## Context

The backend runs end-to-end but is operationally opaque: there is no logging framework, no way to
correlate the lines of one trial across the HTTP edge, the MCP edge, and the LangGraph nodes, no
metrics, and no consistent retry/timeout policy. The cross-cutting observability work touches many
layers and makes several architectural choices that future contributors would otherwise re-litigate.
This ADR records those choices once, as a single coherent seam (mirroring ADR-0001/0002/0003, each
capturing one decision).

The forces: this is a single-process, mostly-mock, credential-free system that must stay easy to run
locally, yet it is heading for a real-tenant deployment where operators need to see what a trial did
and why. We want operational visibility without dragging in a collector/backend or a heavy dependency
that contradicts the project's scope discipline.

## Decision

1. **Structured logging via the stdlib over structlog/OpenTelemetry.** A thin `JsonFormatter` plus an
   idempotent `configure_logging(settings)` in a new cross-cutting `backend/app/observability/` package.
   A ~40-line stdlib formatter captures the `uvicorn`/`fastapi` loggers too and buys essentially what
   structlog would, with no new processor pipeline. `log_level`/`log_format` come from config.
2. **Correlation via `contextvars`, injected at three edges.** `request_id`/`thread_id`/`change_id`
   live in `contextvars` and are merged into every log record by the formatter. They are bound at the
   HTTP middleware, inside the MCP tool/resource closures (the MCP mount is not covered by HTTP
   middleware), and in the graph-node wrapper. Signatures stay clean — IDs are not threaded through
   every call.
3. **Logging is a cross-cutting module, not a port.** There is only ever one implementation; modules
   call `logging.getLogger(__name__)` directly. A `ports/` abstraction would be ceremony with no second
   implementation behind it (contrast the integration and checkpoint ports, which genuinely swap).
4. **Resilience policy: bounded timeouts + idempotency-aware retry.** Every outbound call (LLM,
   knowledge, Graph, GitHub) gets a timeout from config, and a single graph-run wall-clock guard leaves
   the checkpoint resumable on expiry. Retry/backoff (exponential + jitter) lives in
   `BaseIntegrationAdapter`. **Write-idempotency rule:** reads and DRY_RUN predictions retry liberally;
   LIVE non-idempotent writes (`create_*`/`comment_*`) retry **only** on connection-class failures that
   prove the request never reached the server — never on an HTTP status or a post-send read timeout,
   where the write may already have landed.
5. **Metrics as an in-process registry exposed via an MCP resource.** A small thread-safe
   counter/timer registry, surfaced as `court://metrics` (consistent with the MCP-primary surface;
   REST stays health-only), gated by `metrics_enabled`.
6. **Circuit breaker and OpenTelemetry are explicitly deferred.** Both are over-scoped for a
   single-process, mostly-mock deployment. The seams are left clean: the in-process registry is where an
   OTLP/Prometheus exporter would later attach, and the retry helper is where a breaker would wrap.

## Consequences

- One coherent observability seam lands across two work tracks (logging/correlation/metrics and
  resilience/error-handling) without re-deciding these points per PR.
- Operators get correlated structured logs and at-a-glance metrics with zero new infrastructure and no
  change to the credential-free local demo (safe defaults).
- The `observability/` package becomes the single home for cross-cutting concerns; nodes, services, and
  adapters log through `getLogger(__name__)` and stay transparent.
- Deferring OTel/Prometheus/circuit-breaker keeps scope tight; adopting them later is an additive change
  at the documented seams, not a rewrite.
- The write-idempotency rule constrains how retry may be applied to live writes — adapter authors must
  classify each write accordingly.
