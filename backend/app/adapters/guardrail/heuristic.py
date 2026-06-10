"""Offline input shield — the credential-free default guardrail.

It flags the common, well-known prompt-injection phrasings (instruction overrides, role flips,
fake system prompts, delimiter break-outs). This is a deliberately small, transparent stand-in for a
managed shield (Azure AI Content Safety Prompt Shields) — it catches obvious attacks so local and
CI runs are screened, but it is not a substitute for the managed shield in production.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.domain import SOURCE_HEURISTIC, ShieldVerdict
from app.ports.guardrail import GuardrailPort

# (category, pattern source). Patterns are case-insensitive and match the recurring shapes of
# injection attempts seen in third-party content (emails, documents, meeting notes) fed to an LLM.
_RULES: list[tuple[str, str]] = [
    ("instruction_override", r"\bignore\s+(all\s+|any\s+)?(previous|prior|above)\b.*\binstruction"),
    ("instruction_override", r"\bdisregard\s+(the\s+)?(above|previous|prior|earlier)\b"),
    ("instruction_override", r"\bforget\s+(everything|all|the above|previous instructions)\b"),
    ("new_instructions", r"\bnew\s+instructions?\s*:"),
    ("role_override", r"\byou\s+are\s+now\b"),
    ("role_override", r"\bact\s+as\b.*\b(admin|administrator|developer|root|system)\b"),
    ("fake_system_prompt", r"\bsystem\s+prompt\b"),
    ("fake_role_marker", r"(?m)^\s*(system|assistant|developer)\s*:"),
    ("delimiter_breakout", r"</?\s*(untrusted_data|system|instructions?)\s*>"),
]
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (category, re.compile(src, re.I)) for category, src in _RULES
]


class HeuristicGuardrail(GuardrailPort):
    """Pattern-matches untrusted text for the well-known prompt-injection shapes."""

    def screen_input(self, *, user_text: str, documents: Sequence[str] = ()) -> ShieldVerdict:
        haystack = "\n".join(str(b) for b in (user_text, *documents) if b)
        categories = sorted({cat for cat, pattern in _PATTERNS if pattern.search(haystack)})
        return ShieldVerdict(
            flagged=bool(categories), categories=categories, source=SOURCE_HEURISTIC
        )
