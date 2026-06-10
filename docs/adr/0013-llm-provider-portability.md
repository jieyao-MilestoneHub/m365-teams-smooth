# ADR-0013: LLM provider portability and deferred reliability hardening

- **Status:** Accepted
- **Date:** 2026-06-10

## Context

The court calls one real LLM provider (Azure OpenAI) behind the `LLMProvider` port, with an
offline fake as the credential-free default. An audit of the major platforms' production guidance
(Azure OpenAI, OpenAI, Anthropic — first-party and as served via AWS Bedrock and GCP Vertex AI)
surfaced a set of capabilities a portable, enterprise-ready LLM layer eventually needs, and a set
of reliability features whose cost is not justified at the current scale. This ADR records both:
what the port must be able to absorb without redesign, and what is deliberately deferred so future
contributors don't re-litigate the omissions as oversights.

The forces: the engine must stay runnable locally with zero credentials and reproducible trials;
every LLM operation already degrades to a deterministic baseline, which caps the blast radius of
provider failures; and the platforms differ materially in authentication, model identity,
throttling signals, and feature surface, so premature abstraction would encode one vendor's shape.

## Decision

**The port models intent, not provider mechanism.** `LlmRequest` carries a cacheable prefix, a
volatile suffix, a plain-JSON schema, and a token cap; adapters compile these to whatever their
platform offers. Structured output uses the *intersection* schema subset (every property required,
`additionalProperties: false`, no defaults, free-form objects as JSON-encoded strings) that Azure
OpenAI strict mode, Anthropic `output_config.format`, and Gemini `responseSchema` all accept — one
schema works on any future adapter, and client-side validation stays regardless.

**What a future second adapter must account for** (recorded now, built when needed):

- *Credentials are providers, not strings.* Azure uses Entra ID bearer tokens (already keyless
  here), AWS signs whole requests (SigV4), GCP uses Application Default Credentials. All three
  rotate/expire, so an adapter takes a credential **source**; a static key is the special case.
- *Model identity is platform-scoped.* The same model is `gpt-4o` (a deployment name), an
  `anthropic.…-v1:0` ID with a routing prefix (`us.`/`eu.`/`global.` — the prefix is also the
  data-residency selector), or an `@date`-versioned Vertex ID. A logical-model → platform-ID
  mapping belongs in config, not code.
- *Throttling is one concept with three spellings.* HTTP 429 with `retry-after(-ms)`,
  `ThrottlingException`, and `RESOURCE_EXHAUSTED` should normalize to a single retryable error
  carrying the server-supplied delay. Exactly **one** layer owns retries — today the provider SDK
  (configured, not implicit); a port-level policy would first disable the SDK's own retries.
- *Feature surfaces differ even for the same model.* Prompt caching, batch endpoints, payload
  ceilings, and token-counting routes vary per platform; an adapter advertises capabilities and
  callers degrade, mirroring the integration registry's design.

**Deliberately deferred**, with the reasoning:

- **Circuit breaker / degraded mode.** Every LLM call already falls back deterministically per
  call; a breaker would only save latency under sustained outage, which the graph timeout already
  bounds. Revisit when LLM calls sit on a user-facing latency path.
- **Streaming.** Worth adopting when responses approach provider timeout horizons (~10 minutes)
  or large token budgets; court calls are capped at ~1K output tokens with a 30s client timeout.
- **Batch APIs.** The pipeline is interactive (a trial blocks on its verdict); there is no
  offline corpus work to route to a cheaper queue yet.
- **Prompt-side PII scrubbing.** Logs are redacted and untrusted content is fenced and screened;
  scrubbing the prompts themselves would degrade evidence fidelity for the approvers. Revisit if
  a deployment's data-handling terms require it.
- **A second live adapter (Bedrock/Vertex).** No deployment need; the seams above are the
  insurance that adding one stays a one-module, registry-style change.

## Consequences

Easier: adding a second provider adapter without touching `agent/`, `services/`, or the port;
auditing why a reliability feature is absent; keeping schemas portable because the strict subset
is enforced at the source.

Harder / accepted: the intersection schema subset forbids provider-specific schema features (e.g.
numeric constraints) — validation of those stays client-side; deferring the breaker means a
sustained provider outage degrades every trial to its deterministic baseline (visible in
`agentic.*.fallbacks` metrics) rather than failing fast.
