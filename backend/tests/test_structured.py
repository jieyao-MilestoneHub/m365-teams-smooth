"""schema_of renders strict-mode schemas; parse_json/decode_json_object read responses back."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.adapters.parsers.llm_backed import _LlmParse
from app.agent.agentic.gatherer import _LlmGather, _LlmRead
from app.agent.agentic.planner import _LlmPlan
from app.llm.structured import (
    decode_json_object,
    extract_json,
    parse_json,
    schema_of,
)


def _walk(node: object) -> list[dict[str, object]]:
    """All dict nodes in a schema tree."""
    if isinstance(node, dict):
        return [node, *[n for v in node.values() for n in _walk(v)]]
    if isinstance(node, list):
        return [n for item in node for n in _walk(item)]
    return []


@pytest.mark.parametrize("model", [_LlmGather, _LlmPlan, _LlmParse])
def test_schema_is_strict(model: type) -> None:
    schema = schema_of(model)
    for node in _walk(schema):
        assert "default" not in node
        if node.get("type") == "object":
            properties = node.get("properties")
            assert isinstance(properties, dict) and properties
            assert node["additionalProperties"] is False
            required = node["required"]
            assert isinstance(required, list)
            assert sorted(required) == sorted(properties)


def test_free_form_params_travel_as_encoded_strings() -> None:
    schema: Any = schema_of(_LlmGather)
    assert schema["$defs"]["_LlmRead"]["properties"]["params"]["type"] == "string"


def test_decode_json_object_round_trips_the_wire_form() -> None:
    read = _LlmRead.model_validate(
        {"system": "github", "name": "list_blockers", "params": '{"milestone": "Launch"}'}
    )
    assert read.params == {"milestone": "Launch"}
    # Prose-returning providers still hand over plain dicts; those pass through unchanged.
    assert decode_json_object({"a": 1}) == {"a": 1}


def test_parse_json_reads_pure_json_and_falls_back_to_extraction() -> None:
    assert parse_json('{"a": 1}') == {"a": 1}
    assert parse_json('Sure! ```json\n{"a": 1}\n``` hope that helps') == {"a": 1}
    with pytest.raises(ValueError):
        parse_json("no json here")


def test_extract_json_still_tolerates_fences() -> None:
    assert extract_json('```json\n{"b": 2}\n```') == {"b": 2}


def test_strict_schemas_stay_valid_json() -> None:
    # The schema is sent verbatim to the provider; it must be plain-JSON serializable.
    for model in (_LlmGather, _LlmPlan, _LlmParse):
        json.dumps(schema_of(model))
