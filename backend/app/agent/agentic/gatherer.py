"""Prosecutor: agentic evidence gathering — the LLM chooses which read capabilities to query.

The wrapped deterministic gatherer always runs first, so the subject's core evidence and the tags
policy matches are reproducible regardless of the LLM. The LLM then acts as the Prosecutor: shown
the registry's read catalog and what was already gathered, it selects up to ``max_reads``
additional reads (each validated against the catalog before execution — the hallucination guard
extends to tool selection) and contributes a short impact assessment. Any LLM failure leaves the
deterministic evidence untouched.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.agent.agentic.structured import extract_json
from app.agent.nodes.impact import Gatherer
from app.domain import Capability, CapabilityKind, Change, EvidenceItem, ImpactEvidence
from app.domain.errors import IntegrationError
from app.observability import metrics
from app.ports.integration import ReadQuery
from app.ports.knowledge import KnowledgePort
from app.ports.llm import LLMProvider
from app.ports.registry import IntegrationRegistry

logger = logging.getLogger(__name__)

_MAX_ASSESSMENT_CHARS = 600


class _LlmRead(BaseModel):
    system: str
    name: str
    params: dict[str, object] = Field(default_factory=dict)


class _LlmGather(BaseModel):
    reads: list[_LlmRead] = Field(default_factory=list)
    assessment: str = ""


class LlmEvidenceGatherer:
    """Wraps a deterministic gatherer with an LLM-driven, validated read-selection loop."""

    def __init__(
        self,
        llm: LLMProvider,
        fallback: Gatherer,
        *,
        max_reads: int = 5,
    ) -> None:
        self._llm = llm
        self._fallback = fallback
        self._max_reads = max_reads

    def __call__(
        self,
        change: Change,
        registry: IntegrationRegistry,
        knowledge: KnowledgePort,
        errors: list[str],
    ) -> ImpactEvidence:
        evidence = self._fallback(change, registry, knowledge, errors)
        try:
            extra = self._agentic_items(change, registry, evidence, errors)
        except Exception as exc:  # noqa: BLE001 — an unsure Prosecutor adds nothing
            logger.warning("agentic.gather_fallback", extra={"error": str(exc)})
            metrics.increment("agentic.gather.fallbacks")
            return evidence
        evidence.items.extend(extra)
        return evidence

    # --- the agentic loop -------------------------------------------------------------------

    def _agentic_items(
        self,
        change: Change,
        registry: IntegrationRegistry,
        gathered: ImpactEvidence,
        errors: list[str],
    ) -> list[EvidenceItem]:
        catalog = {
            (c.system, c.name): c
            for c in registry.capabilities()
            if c.kind is CapabilityKind.READ
        }
        if not catalog:
            return []

        text = self._llm.complete(
            self._user_prompt(change, gathered), system=self._system_prompt(catalog)
        )
        result = _LlmGather.model_validate(extract_json(text))

        items: list[EvidenceItem] = []
        executed: set[tuple[str, str]] = set()
        for read in result.reads:
            key = (read.system, read.name)
            if len(executed) >= self._max_reads:
                errors.append(f"agentic reads capped at {self._max_reads}; skipped {read.name}")
                break
            if key in executed:
                continue
            capability = catalog.get(key)
            if capability is None:
                errors.append(f"rejected unregistered agentic read {read.system}.{read.name}")
                continue
            if missing := self._missing_params(capability, read.params):
                errors.append(f"agentic read {read.name} missing required params {missing}")
                continue
            adapter = registry.get(read.system)
            if adapter is None:
                continue
            executed.add(key)
            metrics.increment("agentic.reads")
            try:
                data = adapter.read(ReadQuery(capability=read.name, params=read.params)).data
            except IntegrationError as exc:
                errors.append(f"agentic read failed on {read.system}.{read.name}: {exc}")
                continue
            if data:
                items.append(
                    EvidenceItem(
                        system=read.system,
                        kind="agentic",
                        summary=f"[prosecutor] {read.name}",
                        data=data,
                    )
                )

        if result.assessment.strip():
            items.append(
                EvidenceItem(
                    system="prosecutor",
                    kind="assessment",
                    summary=result.assessment.strip()[:_MAX_ASSESSMENT_CHARS],
                )
            )
        return items

    @staticmethod
    def _missing_params(capability: Capability, params: dict[str, object]) -> list[str]:
        required = capability.params_schema.get("required", []) if capability.params_schema else []
        if not isinstance(required, list):
            return []
        return [str(k) for k in required if k not in params]

    @staticmethod
    def _user_prompt(change: Change, gathered: ImpactEvidence) -> str:
        already = "; ".join(f"{i.system}/{i.kind}: {i.summary}" for i in gathered.items) or "none"
        return (
            f"Change request ({change.subject}): {change.raw_request}\n"
            f"Due by: {change.due_by or 'unspecified'}\n"
            f"Evidence already gathered: {already}"
        )

    def _system_prompt(self, catalog: dict[tuple[str, str], Capability]) -> str:
        lines = []
        for (system, name), cap in sorted(catalog.items()):
            required = cap.params_schema.get("required", []) if cap.params_schema else []
            names = [str(k) for k in required] if isinstance(required, list) else []
            req = f" (required params: {', '.join(names)})" if names else ""
            lines.append(f"- {system} :: {name}: {cap.description or 'no description'}{req}")
        shape = (
            '{"reads": [{"system": str, "name": str, "params": object}], "assessment": str}'
        )
        return (
            "You are the Prosecutor in a change-governance court: your job is to surface "
            "second-order consequences of a risky change before it executes.\n"
            f"Select up to {self._max_reads} ADDITIONAL read capabilities (beyond the evidence "
            "already gathered) that would reveal blockers, conflicts, commitments, or exposure. "
            "Only use capabilities from this catalog:\n" + "\n".join(lines) + "\n"
            "Then write a one-paragraph impact assessment of the strongest risk you see.\n"
            f"Respond with ONLY a JSON object of this shape: {shape}"
        )
