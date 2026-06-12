"""Defender: agentic plan generation — the LLM drafts the plan, governance keeps the verdict.

The wrapped deterministic planner runs first and its plan *kind* is binding: when it refuses the
request as posed (a safe alternative), the LLM may enrich the alternative but can never turn it
back into the request — refusal authority stays deterministic. Every step the LLM proposes is
validated against the registry's write catalog (existence + required params) before the plan is
accepted; anything invalid falls back to the deterministic plan unchanged.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field, field_validator

from app.agent.agentic.precedents import render_precedents
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
    param_violations,
)
from app.llm.structured import decode_json_object, parse_json, schema_of
from app.llm.untrusted import HARDENING, fence
from app.observability import metrics
from app.ports.guardrail import GuardrailPort
from app.ports.llm import LLMProvider, LlmRequest
from app.ports.memory import MemoryPort
from app.ports.registry import IntegrationRegistry

logger = logging.getLogger(__name__)

_MAX_STEPS = 8


class _LlmStep(BaseModel):
    system: str
    name: str
    params: dict[str, object] = Field(default_factory=dict)

    # In strict structured-output mode the free-form params object travels JSON-encoded.
    @field_validator("params", mode="before")
    @classmethod
    def _decode_params(cls, value: object) -> object:
        return decode_json_object(value)


class _LlmPlan(BaseModel):
    steps: list[_LlmStep] = Field(default_factory=list)
    rationale: str = ""


_PLAN_SCHEMA = schema_of(_LlmPlan)


class LlmPlanner:
    """Wraps a deterministic planner; the LLM proposes steps within the baseline's plan kind."""

    def __init__(
        self,
        llm: LLMProvider,
        registry: IntegrationRegistry,
        fallback: Planner,
        *,
        memory: MemoryPort | None = None,
        guardrail: GuardrailPort | None = None,
        guardrail_blocking: bool = True,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._fallback = fallback
        self._memory = memory
        self._guardrail = guardrail
        self._block = guardrail_blocking

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

        # The request and impact evidence are third-party content; screen before the Defender
        # drafts a plan over them. A flag keeps the deterministic baseline plan.
        if self._guardrail is not None and self._block:
            docs = [i.summary for i in impact.items]
            verdict = self._guardrail.screen_input(user_text=change.raw_request, documents=docs)
            if verdict.flagged:
                logger.warning("agentic.guardrail_blocked", extra={"cats": verdict.categories})
                metrics.increment("guardrail.input_blocked")
                return None

        text = self._llm.generate(
            LlmRequest(
                prompt=self._user_prompt(change, impact, baseline),
                cacheable_prefix=self._system_prompt(catalog),
                system_suffix=self._stance(baseline.kind),
                json_schema=_PLAN_SCHEMA,
                schema_name="defender_plan",
            )
        ).text
        result = _LlmPlan.model_validate(parse_json(text))
        if not result.steps or len(result.steps) > _MAX_STEPS:
            metrics.increment("agentic.plan.fallbacks")
            return None

        steps: list[ExecutionStep] = []
        for index, step in enumerate(result.steps, start=1):
            capability = catalog.get((step.system, step.name))
            if capability is None or param_violations(capability, step.params):
                # One hallucinated, underspecified, or malformed step invalidates the whole plan:
                # a partial plan could execute a different change than the one reviewed, and an
                # unusable value (e.g. a non-numeric issue ref) would fail at execution instead.
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
    def _constraint_hints(capability: Capability) -> list[str]:
        """Render the catalog's value constraints so the Defender drafts usable params."""
        properties = capability.params_schema.get("properties", {})
        if not isinstance(properties, dict):
            return []
        hints: list[str] = []
        for key, constraint in properties.items():
            if not isinstance(constraint, dict):
                continue
            if constraint.get("format") == "date":
                hints.append(f"{key} is an ISO date")
            pattern = constraint.get("pattern")
            if isinstance(pattern, str):
                hints.append(f"{key} matches {pattern}")
        return hints

    def _user_prompt(
        self, change: Change, impact: ImpactEvidence, baseline: ExecutionPlan
    ) -> str:
        evidence = "; ".join(f"{i.system}/{i.kind}: {i.summary}" for i in impact.items) or "none"
        base = "; ".join(f"{s.capability.system}.{s.capability.name}" for s in baseline.steps)
        prompt = (
            f"Change subject: {change.subject}\n"
            f"Change request: {fence('request', change.raw_request)}\n"
            f"Due by: {change.due_by or 'unspecified'}\n"
            f"Impact evidence: {fence('evidence', evidence)}\n"
            f"Baseline plan ({baseline.kind.value}): {base or 'none'}\n"
            f"Baseline rationale: {baseline.rationale}"
        )
        precedents = render_precedents(self._memory, change.subject or "", impact.tags)
        return f"{prompt}\n{precedents}" if precedents else prompt

    def _system_prompt(self, catalog: dict[tuple[str, str], Capability]) -> str:
        """The stable role + catalog block — a cacheable prefix shared across trials."""
        lines = []
        for (system, name), cap in sorted(catalog.items()):
            required = cap.params_schema.get("required", []) if cap.params_schema else []
            names = [str(k) for k in required] if isinstance(required, list) else []
            req = f" (required params: {', '.join(names)})" if names else ""
            hints = self._constraint_hints(cap)
            req += f" [{'; '.join(hints)}]" if hints else ""
            lines.append(f"- {system} :: {name}: {cap.description or 'no description'}{req}")
        shape = (
            '{"steps": [{"system": str, "name": str, "params": JSON-encoded object string}], '
            '"rationale": str}'
        )
        return (
            "You are the Defender in a change-governance court: you produce the execution plan "
            "the approvers will review.\n"
            f"{HARDENING}\n"
            f"Use at most {_MAX_STEPS} steps, ONLY with capabilities from this catalog:\n"
            + "\n".join(lines)
            + "\nInclude every required param. Explain the plan in one-paragraph rationale.\n"
            f"Respond with ONLY a JSON object of this shape: {shape}"
        )

    @staticmethod
    def _stance(kind: PlanKind) -> str:
        """The per-trial stance — volatile, so it rides after the cacheable prefix."""
        if kind is PlanKind.SAFE_ALTERNATIVE:
            return (
                "The court has REFUSED the request as posed. Draft the strongest SAFE ALTERNATIVE "
                "plan: it must not implement the original request, only the safer path."
            )
        return "Draft the most complete feasible plan for the request."
