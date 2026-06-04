"""Structured-output helper for the agentic roles: pull a JSON object out of model text.

Mirrors the parser-side extraction (``app/adapters/parsers/llm_backed.py``) without importing the
adapter layer — ``agent/`` depends on ports only.
"""

from __future__ import annotations

import json


def extract_json(text: str) -> object:
    """Pull the JSON object out of a model response (tolerating code fences and prose)."""
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s[:4].lower() == "json":
            s = s[4:]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    return json.loads(s[start : end + 1])
