"""Structured-output helpers for the LLM-backed roles (Prosecutor, Defender, parser).

``schema_of`` renders a Pydantic wire model as a strict-mode JSON Schema for native structured
output; ``parse_json`` reads the response back, tolerating prose from providers that don't honor
schemas (the offline fake, test stubs). Everything here is plain JSON — no SDK types — so both
the agent roles and the LLM-backed adapters can share it without crossing a layer boundary.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

_ENCODED_OBJECT = {
    "type": "string",
    "description": "A JSON-encoded object, e.g. \"{\\\"key\\\": \\\"value\\\"}\".",
}


def schema_of(model: type[BaseModel]) -> dict[str, object]:
    """Render ``model`` as a JSON Schema valid for strict structured output.

    Strict mode (Azure OpenAI ``strict: true``; the same subset is accepted by Anthropic's
    ``output_config.format`` and Gemini's ``responseSchema``) requires every object to list all
    properties as required with ``additionalProperties: false``, and rejects defaults and
    free-form objects. Free-form ``dict`` fields therefore travel as JSON-encoded strings —
    pair them with ``decode_json_object`` on the Pydantic side.
    """
    strict = _strictify(model.model_json_schema())
    if not isinstance(strict, dict):  # a model schema is always an object — keep mypy honest
        raise TypeError(f"unexpected schema shape for {model.__name__}")
    return strict


def _strictify(node: object) -> object:
    if isinstance(node, list):
        return [_strictify(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {key: _strictify(value) for key, value in node.items() if key != "default"}
    if out.get("type") == "object":
        properties = out.get("properties")
        if isinstance(properties, dict) and properties:
            out["additionalProperties"] = False
            out["required"] = sorted(properties)
        else:
            return dict(_ENCODED_OBJECT)
    return out


def decode_json_object(value: object) -> object:
    """Decode the strict-mode wire form of a free-form dict field (a JSON-encoded string)."""
    if isinstance(value, str):
        return json.loads(value)
    return value


def parse_json(text: str) -> object:
    """Parse a model response as JSON, falling back to extraction for prose-returning providers."""
    try:
        return json.loads(text)
    except ValueError:
        return extract_json(text)


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
