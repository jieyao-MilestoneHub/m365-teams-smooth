"""Defender plan generation: validated steps, binding refusal, fallback on any doubt."""

from __future__ import annotations

import json

from app.agent.agentic.planner import LlmPlanner
from app.domain import (
    Capability,
    CapabilityKind,
    CapabilityRef,
    Change,
    ExecutionPlan,
    ExecutionStep,
    ImpactEvidence,
    PlanKind,
)
from app.ports.llm import LLMProvider


class _ScriptedLLM(LLMProvider):
    def __init__(self, response: str) -> None:
        self._response = response
        self.prompts: list[tuple[str, str]] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.prompts.append((prompt, system or ""))
        return self._response


class _Registry:
    def __init__(self, caps: list[Capability]) -> None:
        self._caps = caps

    def capabilities(self) -> list[Capability]:
        return self._caps

    def get(self, system: str) -> None:
        return None


def _write_cap(
    system: str,
    name: str,
    *,
    required: list[str] | None = None,
    properties: dict[str, object] | None = None,
) -> Capability:
    schema: dict[str, object] = {}
    if required:
        schema["required"] = required
    if properties:
        schema["properties"] = properties
    return Capability(
        system=system, name=name, kind=CapabilityKind.WRITE, description="d", params_schema=schema
    )


def _baseline(kind: PlanKind) -> ExecutionPlan:
    return ExecutionPlan(
        kind=kind,
        steps=[
            ExecutionStep(
                step_id="b1",
                capability=CapabilityRef(system="github", name="github.update_milestone_due"),
                params={"milestone": "Launch"},
            )
        ],
        rationale="baseline rationale",
        supersedes_request=kind is PlanKind.SAFE_ALTERNATIVE,
    )


def _planner(response: str, kind: PlanKind, caps: list[Capability]) -> LlmPlanner:
    return LlmPlanner(
        _ScriptedLLM(response),
        _Registry(caps),  # type: ignore[arg-type]
        fallback=lambda change, impact: _baseline(kind),
    )


_CHANGE = Change(change_id="c1", raw_request="slip the launch", subject="launch")
_IMPACT = ImpactEvidence()


def _plan_json(steps: list[dict[str, object]], rationale: str = "drafted") -> str:
    return json.dumps({"steps": steps, "rationale": rationale})


def test_valid_llm_plan_is_adopted_with_rationale() -> None:
    caps = [_write_cap("teams", "teams.update_announcement", required=["channel"])]
    response = _plan_json(
        [{"system": "teams", "name": "teams.update_announcement", "params": {"channel": "x"}}]
    )
    plan = _planner(response, PlanKind.FEASIBLE, caps)(_CHANGE, _IMPACT)

    assert [s.capability.name for s in plan.steps] == ["teams.update_announcement"]
    assert plan.steps[0].step_id == "s1"
    assert plan.rationale == "drafted"
    assert plan.kind is PlanKind.FEASIBLE


def test_refusal_is_binding_llm_cannot_downgrade_to_feasible() -> None:
    # The deterministic baseline refused the request; whatever the LLM drafts stays a
    # safe alternative — the kind (and supersedes flag) come from the baseline, not the LLM.
    caps = [_write_cap("crm", "crm.add_commitment_note")]
    response = _plan_json([{"system": "crm", "name": "crm.add_commitment_note"}])
    plan = _planner(response, PlanKind.SAFE_ALTERNATIVE, caps)(_CHANGE, _IMPACT)

    assert plan.kind is PlanKind.SAFE_ALTERNATIVE
    assert plan.supersedes_request is True


def test_hallucinated_step_rejects_the_whole_plan() -> None:
    caps = [_write_cap("teams", "teams.update_announcement")]
    response = _plan_json(
        [
            {"system": "teams", "name": "teams.update_announcement"},
            {"system": "github", "name": "github.delete_repository"},  # not in the catalog
        ]
    )
    plan = _planner(response, PlanKind.FEASIBLE, caps)(_CHANGE, _IMPACT)

    assert plan.rationale == "baseline rationale"  # full fallback, no partial plan
    assert [s.step_id for s in plan.steps] == ["b1"]


def test_missing_required_params_rejects_the_plan() -> None:
    caps = [_write_cap("outlook", "outlook.create_event", required=["title", "start"])]
    response = _plan_json([{"system": "outlook", "name": "outlook.create_event"}])
    plan = _planner(response, PlanKind.FEASIBLE, caps)(_CHANGE, _IMPACT)

    assert plan.rationale == "baseline rationale"


def test_malformed_param_value_rejects_the_plan() -> None:
    # Present-but-unusable values (a non-numeric issue ref) fall back instead of reaching
    # execution and failing there.
    caps = [
        _write_cap(
            "github",
            "github.comment_issue",
            required=["issue", "body"],
            properties={"issue": {"pattern": "^[0-9]+$"}},
        )
    ]
    response = _plan_json(
        [
            {
                "system": "github",
                "name": "github.comment_issue",
                "params": {"issue": "Milestone 'Launch'", "body": "moved"},
            }
        ]
    )
    plan = _planner(response, PlanKind.FEASIBLE, caps)(_CHANGE, _IMPACT)

    assert plan.rationale == "baseline rationale"  # full fallback, no partial plan


def test_prompt_renders_value_constraint_hints() -> None:
    caps = [
        _write_cap(
            "github",
            "github.update_milestone_due",
            required=["milestone", "due_on"],
            properties={"due_on": {"format": "date"}},
        )
    ]
    llm = _ScriptedLLM(_plan_json([]))
    planner = LlmPlanner(
        llm,
        _Registry(caps),  # type: ignore[arg-type]
        fallback=lambda change, impact: _baseline(PlanKind.FEASIBLE),
    )
    planner(_CHANGE, _IMPACT)

    _, system = llm.prompts[0]
    assert "due_on is an ISO date" in system


def test_empty_or_oversized_plans_fall_back() -> None:
    caps = [_write_cap("teams", "teams.update_announcement")]
    empty = _planner(_plan_json([]), PlanKind.FEASIBLE, caps)(_CHANGE, _IMPACT)
    assert empty.rationale == "baseline rationale"

    too_many: list[dict[str, object]] = [
        {"system": "teams", "name": "teams.update_announcement"}
    ] * 9
    oversized = _planner(_plan_json(too_many), PlanKind.FEASIBLE, caps)(_CHANGE, _IMPACT)
    assert oversized.rationale == "baseline rationale"


def test_llm_garbage_falls_back() -> None:
    caps = [_write_cap("teams", "teams.update_announcement")]
    plan = _planner("not json", PlanKind.FEASIBLE, caps)(_CHANGE, _IMPACT)
    assert plan.rationale == "baseline rationale"


def test_prompt_carries_stance_catalog_and_baseline() -> None:
    caps = [_write_cap("teams", "teams.update_announcement")]
    llm = _ScriptedLLM(_plan_json([]))
    planner = LlmPlanner(
        llm,
        _Registry(caps),  # type: ignore[arg-type]
        fallback=lambda change, impact: _baseline(PlanKind.SAFE_ALTERNATIVE),
    )
    planner(_CHANGE, _IMPACT)

    prompt, system = llm.prompts[0]
    assert "REFUSED" in system  # safe-alternative stance is explicit
    assert "teams :: teams.update_announcement" in system
    assert "github.update_milestone_due" in prompt  # baseline plan is shown
    assert "baseline rationale" in prompt
