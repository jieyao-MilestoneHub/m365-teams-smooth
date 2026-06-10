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
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field, field_validator

from app.agent.agentic.precedents import render_precedents
from app.agent.agentic.structured import decode_json_object, parse_json, schema_of
from app.agent.agentic.untrusted import HARDENING, fence
from app.agent.nodes.impact import Gatherer
from app.domain import Capability, CapabilityKind, Change, EvidenceItem, ImpactEvidence
from app.domain.errors import IntegrationError
from app.observability import metrics
from app.ports.guardrail import GuardrailPort
from app.ports.integration import ReadQuery
from app.ports.knowledge import KnowledgePort
from app.ports.llm import LLMProvider, LlmRequest
from app.ports.memory import MemoryPort
from app.ports.registry import IntegrationRegistry

logger = logging.getLogger(__name__)

_MAX_ASSESSMENT_CHARS = 600


class _LlmRead(BaseModel):
    system: str
    name: str
    params: dict[str, object] = Field(default_factory=dict)

    # In strict structured-output mode the free-form params object travels JSON-encoded.
    @field_validator("params", mode="before")
    @classmethod
    def _decode_params(cls, value: object) -> object:
        return decode_json_object(value)


class _LlmGather(BaseModel):
    reads: list[_LlmRead] = Field(default_factory=list)
    assessment: str = ""


_GATHER_SCHEMA = schema_of(_LlmGather)


class LlmEvidenceGatherer:
    """Wraps a deterministic gatherer with an LLM-driven, validated read-selection loop."""

    def __init__(
        self,
        llm: LLMProvider,
        fallback: Gatherer,
        *,
        max_reads: int = 5,
        memory: MemoryPort | None = None,
        guardrail: GuardrailPort | None = None,
        guardrail_blocking: bool = True,
    ) -> None:
        self._llm = llm
        self._fallback = fallback
        self._max_reads = max_reads
        self._memory = memory
        self._guardrail = guardrail
        self._block = guardrail_blocking

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

        # The request and gathered evidence come from third parties; screen for prompt injection
        # before the Prosecutor reasons over them. A flag falls back to the deterministic evidence.
        if self._guardrail is not None and self._block:
            docs = [i.summary for i in gathered.items]
            verdict = self._guardrail.screen_input(user_text=change.raw_request, documents=docs)
            if verdict.flagged:
                logger.warning("agentic.guardrail_blocked", extra={"cats": verdict.categories})
                metrics.increment("guardrail.input_blocked")
                return []

        text = self._llm.generate(
            LlmRequest(
                prompt=self._user_prompt(change, gathered),
                cacheable_prefix=self._system_prompt(catalog),
                json_schema=_GATHER_SCHEMA,
                schema_name="prosecutor_reads",
            )
        ).text
        result = _LlmGather.model_validate(parse_json(text))

        # Validate sequentially (deterministic — this mutates errors/cap/dedup), then execute the
        # surviving reads. Validation never touches the network, so it stays cheap and ordered.
        planned: list[_LlmRead] = []
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
            if registry.get(read.system) is None:
                continue
            executed.add(key)
            planned.append(read)

        # The validated reads are independent network calls — run them with bounded concurrency.
        # pool.map preserves submission order, so the resulting evidence (and the errors appended
        # below) stay deterministic; a failed read degrades gracefully exactly as before.
        items: list[EvidenceItem] = []
        if planned:
            metrics.increment("agentic.reads", len(planned))
            with ThreadPoolExecutor(max_workers=min(len(planned), self._max_reads)) as pool:
                outcomes = list(pool.map(lambda r: self._run_read(registry, r), planned))
            for read, (ok, payload) in zip(planned, outcomes, strict=True):
                if not ok:
                    errors.append(f"agentic read failed on {read.system}.{read.name}: {payload}")
                elif isinstance(payload, dict) and payload:
                    items.append(
                        EvidenceItem(
                            system=read.system,
                            kind="agentic",
                            summary=f"[prosecutor] {read.name}",
                            data=payload,
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
    def _run_read(
        registry: IntegrationRegistry, read: _LlmRead
    ) -> tuple[bool, dict[str, object] | str]:
        """Execute one validated read (called from the thread pool). Returns (ok, data | error)."""
        adapter = registry.get(read.system)
        if adapter is None:  # validated as present, but stay defensive on the worker thread
            return False, "adapter unavailable"
        try:
            return True, adapter.read(ReadQuery(capability=read.name, params=read.params)).data
        except IntegrationError as exc:
            return False, str(exc)

    def _user_prompt(self, change: Change, gathered: ImpactEvidence) -> str:
        already = "; ".join(f"{i.system}/{i.kind}: {i.summary}" for i in gathered.items) or "none"
        prompt = (
            f"Change subject: {change.subject}\n"
            f"Change request: {fence('request', change.raw_request)}\n"
            f"Due by: {change.due_by or 'unspecified'}\n"
            f"Evidence already gathered: {fence('evidence', already)}"
        )
        precedents = render_precedents(self._memory, change.subject or "", gathered.tags)
        return f"{prompt}\n{precedents}" if precedents else prompt

    def _system_prompt(self, catalog: dict[tuple[str, str], Capability]) -> str:
        lines = []
        for (system, name), cap in sorted(catalog.items()):
            required = cap.params_schema.get("required", []) if cap.params_schema else []
            names = [str(k) for k in required] if isinstance(required, list) else []
            req = f" (required params: {', '.join(names)})" if names else ""
            lines.append(f"- {system} :: {name}: {cap.description or 'no description'}{req}")
        shape = (
            '{"reads": [{"system": str, "name": str, "params": JSON-encoded object string}], '
            '"assessment": str}'
        )
        return (
            "You are the Prosecutor in a change-governance court: your job is to surface "
            "second-order consequences of a risky change before it executes.\n"
            f"{HARDENING}\n"
            f"Select up to {self._max_reads} ADDITIONAL read capabilities (beyond the evidence "
            "already gathered) that would reveal blockers, conflicts, commitments, or exposure. "
            "Only use capabilities from this catalog:\n" + "\n".join(lines) + "\n"
            "Then write a one-paragraph impact assessment of the strongest risk you see.\n"
            f"Respond with ONLY a JSON object of this shape: {shape}"
        )
