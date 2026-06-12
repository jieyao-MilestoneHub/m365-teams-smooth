"""Provider-agnostic LLM wire utilities, shared by the agent and the LLM-backed adapters.

Distinct from :mod:`app.adapters.llm` (the concrete providers): nothing here talks to a service.
``structured`` renders wire models into the cross-provider strict JSON-Schema subset and parses
the replies; ``untrusted`` fences third-party content before any LLM reasons over it.
"""
