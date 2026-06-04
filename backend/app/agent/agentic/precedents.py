"""Precedent rendering shared by the agentic roles: bounded, citable prompt text."""

from __future__ import annotations

from app.ports.memory import MemoryPort

_MAX_PRECEDENT_CHARS = 200


def render_precedents(
    memory: MemoryPort | None, subject: str, tags: list[str], *, top_k: int = 3
) -> str:
    """A bounded, citable summary of past rulings for a prompt (empty when none/unavailable)."""
    if memory is None:
        return ""
    try:
        precedents = memory.find_similar(subject, tags, top_k=top_k)
    except Exception:  # noqa: BLE001 — missing memory must never block a trial
        return ""
    lines = [
        f"- [{p.thread_id[:8]}] {p.raw_request[:80]} -> {p.verdict_type or p.status}"
        f" ({p.plan_kind}): {p.rationale}"[:_MAX_PRECEDENT_CHARS]
        for p in precedents
    ]
    return "Past rulings on similar changes:\n" + "\n".join(lines) if lines else ""
