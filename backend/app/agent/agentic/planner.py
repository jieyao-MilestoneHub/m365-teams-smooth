"""Defender: agentic plan generation — the LLM drafts the plan, governance keeps the verdict.

The wrapped deterministic planner runs first and its plan *kind* is binding: when it refuses the
request as posed (a safe alternative), the LLM may enrich the alternative but can never turn it
back into the request — refusal authority stays deterministic. Every step the LLM proposes is
validated against the registry's write catalog (existence + required params) before the plan is
accepted; anything invalid falls back to the deterministic plan unchanged.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.agent.agentic.precedents import render_precedents
from app.agent.agentic.structured import extract_json
from app.agent.nodes.options import Planner
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
from app.observability import metrics
from app.ports.llm import LLMProvider
from app.ports.memory import MemoryPort
from app.ports.registry import IntegrationRegistry

logger = logging.getLogger(__name__)

_MAX_STEPS = 8


class _LlmStep(BaseModel):
    system: str
    name: str
    params: dict[str, object] = Field(default_factory=dict)


class _LlmPlan(BaseModel):
    steps: list[_LlmStep] = Field(default_factory=list)
    rationale: str = ""


class LlmPlanner:
    """Wraps a deterministic planner; the LLM proposes steps within the baseline's plan kind."""

    def __init__(
        self,
        llm: LLMProvider,
        registry: IntegrationRegistry,
        fallback: Planner,
        *,
        memory: MemoryPort | None = None,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._fallback = fallback
        self._memory = memory

    def __call__(self, change: Change, impact: ImpactEvidence) -> ExecutionPlan:
        baseline = self._fallback(change, impact)
        try:
            plan = self._agentic_plan(change, impact, baseline)
        except Exception as exc:  # noqa: BLE001 — an unsure Defender keeps the baseline
            logger.warning("agentic.plan_fallback", extra={"error": str(exc)})
            metrics.increment("agentic.plan.fallbacks")
            return baseline
        return plan if plan is not None else baseline

    def _agentic_plan(
        self, change: Change, impact: ImpactEvidence, baseline: ExecutionPlan
    ) -> ExecutionPlan | None:
        catalog = {
            (c.system, c.name): c
            for c in self._registry.capabilities()
            if c.kind is CapabilityKind.WRITE
        }
        if not catalog:
            return None

        text = self._llm.complete(
            self._user_prompt(change, impact, baseline),
            system=self._system_prompt(catalog, baseline.kind),
        )
        result = _LlmPlan.model_validate(extract_json(text))
        if not result.steps or len(result.steps) > _MAX_STEPS:
            metrics.increment("agentic.plan.fallbacks")
            return None

        steps: list[ExecutionStep] = []
        for index, step in enumerate(result.steps, start=1):
            capability = catalog.get((step.system, step.name))
            if capability is None or self._missing_params(capability, step.params):
                # One hallucinated or underspecified step invalidates the whole plan: a partial
                # plan could execute a different change than the one reviewed.
                logger.warning(
                    "agentic.plan_fallback",
                    extra={"reason": "invalid_step", "step": f"{step.system}.{step.name}"},
                )
                metrics.increment("agentic.plan.fallbacks")
                return None
            steps.append(
                ExecutionStep(
                    step_id=f"s{index}",
                    capability=CapabilityRef(system=step.system, name=step.name),
                    params=step.params,
                )
            )

        rationale = result.rationale.strip() or baseline.rationale
        return ExecutionPlan(
            kind=baseline.kind,  # the deterministic verdict on safety is binding
            steps=steps,
            rationale=rationale,
            supersedes_request=baseline.supersedes_request,
        )

    @staticmethod
    def _missing_params(capability: Capability, params: dict[str, object]) -> list[str]:
        required = capability.params_schema.get("required", []) if capability.params_schema else []
        if not isinstance(required, list):
            return []
        return [str(k) for k in required if k not in params]

    def _user_prompt(
        self, change: Change, impact: ImpactEvidence, baseline: ExecutionPlan
    ) -> str:
        evidence = "; ".join(f"{i.system}/{i.kind}: {i.summary}" for i in impact.items) or "none"
        base = "; ".join(f"{s.capability.system}.{s.capability.name}" for s in baseline.steps)
        prompt = (
            f"Change request ({change.subject}): {change.raw_request}\n"
            f"Due by: {change.due_by or 'unspecified'}\n"
            f"Impact evidence: {evidence}\n"
            f"Baseline plan ({baseline.kind.value}): {base or 'none'}\n"
            f"Baseline rationale: {baseline.rationale}"
        )
        precedents = render_precedents(self._memory, change.subject or "", impact.tags)
        return f"{prompt}\n{precedents}" if precedents else prompt

    def _system_prompt(
        self, catalog: dict[tuple[str, str], Capability], kind: PlanKind
    ) -> str:
        lines = []
        for (system, name), cap in sorted(catalog.items()):
            required = cap.params_schema.get("required", []) if cap.params_schema else []
            names = [str(k) for k in required] if isinstance(required, list) else []
            req = f" (required params: {', '.join(names)})" if names else ""
            lines.append(f"- {system} :: {name}: {cap.description or 'no description'}{req}")
        if kind is PlanKind.SAFE_ALTERNATIVE:
            stance = (
                "The court has REFUSED the request as posed. Draft the strongest SAFE ALTERNATIVE "
                "plan: it must not implement the original request, only the safer path."
            )
        else:
            stance = "Draft the most complete feasible plan for the request."
        shape = (
            '{"steps": [{"system": str, "name": str, "params": object}], "rationale": str}'
        )
        return (
            "You are the Defender in a change-governance court: you produce the execution plan "
            "the approvers will review.\n"
            f"{stance}\n"
            f"Use at most {_MAX_STEPS} steps, ONLY with capabilities from this catalog:\n"
            + "\n".join(lines)
            + "\nInclude every required param. Explain the plan in one-paragraph rationale.\n"
            f"Respond with ONLY a JSON object of this shape: {shape}"
        )
