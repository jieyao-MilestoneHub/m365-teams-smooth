"""Agentic court roles: LLM-driven perception and planning over the registered capabilities.

Every component here follows the same contract: it wraps a deterministic implementation, lets the
LLM reason within validated bounds (capabilities checked against the registry, loop sizes capped),
and falls back to the deterministic result on any failure — so trials stay reproducible offline
and the policy/quorum layer never depends on LLM output.
"""
