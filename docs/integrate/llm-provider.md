# Configuring or swapping the LLM provider

The court runs **with or without** an LLM. Understanding where the model is allowed to act — and
where it never is — tells you exactly what swapping a provider can and cannot change.

## Where the LLM acts (and where it can't)

The model powers the **agentic** parts only ([View ②](../architecture/02-court-pipeline.html),
[ADR-0009](../reference/adr/0009-agentic-roles-and-governed-autonomy.md)):

- **perception** — parsing the raw request into a structured change; choosing which evidence reads
  to make (bounded by a per-trial read budget);
- **generation** — drafting plan wording and summaries.

Risk scoring, quorum, refusal authority, execution gating, and the audit are deterministic and
**never** delegated to the model. Every model output passes the capability hallucination guard
before it can influence a plan. Swapping providers can change phrasing quality — it cannot change
what the court is allowed to do.

## Provider options

| Setup | Configuration | Notes |
| --- | --- | --- |
| **Offline (default)** | leave everything empty | Deterministic parser + fake provider; trials fully reproducible, zero credentials. |
| **Azure OpenAI, keyless** | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` (+ `AZURE_OPENAI_API_VERSION`) | Auth via `DefaultAzureCredential` — `az login` locally, managed identity hosted. No key stored. |
| **Key-based** | the above + `LLM_API_KEY` | Only when keyless auth isn't available. |

`FORCE_ALL_MOCK=true` overrides everything back to offline. `LLM_TIMEOUT_SECONDS` caps each model
call.

## The fallback contract

This is the property to preserve if you touch anything here: **every agentic step has a
deterministic fallback.** On any model failure — timeout, auth, malformed output — the node falls
back to the deterministic path and the trial completes. A misconfigured LLM degrades phrasing,
never availability and never safety.

Watch the fallback health through the `court://metrics` MCP resource: the agentic counters show
whether the model path is actually being taken or silently falling back.

## Swapping in a different provider

The LLM sits behind a port like every other dependency: an adapter under
`backend/app/adapters/llm/` plus its selection in the composition root
(`backend/app/container.py`). A different provider is one more adapter that satisfies the port —
keep its output constrained to the same structured shapes, and keep the fallback contract intact.
The graph and services don't change.

When choosing models, prefer your provider's current general-purpose tier and verify it against
the trials offline first; the parser's structured outputs matter more than raw eloquence.

## See also

- [config-reference.md](config-reference.md) — the full env-var table.
- [View ⑥ — Microsoft platform integration](../architecture/06-platform-integration.html) — the
  Azure OpenAI edge and its keyless posture.
