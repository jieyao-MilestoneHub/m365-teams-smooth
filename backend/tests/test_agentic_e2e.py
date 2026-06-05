"""End-to-end agentic chain through the real graph with a scripted LLM.

This is the deployment-shaped test: the Prosecutor's selected reads and the Defender's drafted
plan flow through intake → impact → options → policy → verdict → execute → verify → audit, the
ruling lands as a precedent, and the next trial's prompts cite it. Hallucinated selections are
rejected mid-chain without failing the trial.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.persistence.db import make_engine, make_session_factory
from app.adapters.persistence.repositories import SqlPrecedentStore
from app.agent.agentic.gatherer import LlmEvidenceGatherer
from app.agent.agentic.planner import LlmPlanner
from app.agent.gatherers import GATHERERS
from app.agent.nodes.impact import Gatherer
from app.agent.nodes.options import Planner
from app.agent.planners import PLANNERS
from app.config import Settings
from app.container import build_court_service
from app.domain import VerdictType
from app.ports.llm import LLMProvider
from app.services.court_service import CourtService
from tests.conftest import build_mock_registry

_REQ = "slip the launch from 2026-06-10 to 2026-06-17"

_GATHER_OK = json.dumps(
    {
        "reads": [
            {"system": "crm", "name": "crm.read_account", "params": {"account": "Customer A"}}
        ],
        "assessment": "the schedule slip risks the customer commitment",
    }
)
_PLAN_OK = json.dumps(
    {
        "steps": [
            {
                "system": "github",
                "name": "github.update_milestone_due",
                "params": {"milestone": "Launch", "due_on": "2026-06-17"},
            }
        ],
        "rationale": "drafted by the defender",
    }
)
_GATHER_HALLUCINATED = json.dumps(
    {"reads": [{"system": "github", "name": "github.read_everything"}], "assessment": ""}
)
_PLAN_HALLUCINATED = json.dumps(
    {"steps": [{"system": "github", "name": "github.delete_repository"}], "rationale": "bad"}
)


class _ScriptedLLM(LLMProvider):
    """Plays back queued responses (gatherer then planner per trial); records every prompt."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[tuple[str, str]] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.prompts.append((prompt, system or ""))
        if not self._responses:
            raise AssertionError("scripted LLM exhausted — unexpected extra call")
        return self._responses.pop(0)


def _agentic_service(db_path: str, llm: _ScriptedLLM) -> CourtService:
    db_url = f"sqlite:///{db_path}"
    memory = SqlPrecedentStore(make_session_factory(make_engine(db_url)))
    registry = build_mock_registry()
    gatherers: dict[str, Gatherer] = {
        subject: LlmEvidenceGatherer(llm, fallback=g, memory=memory)
        for subject, g in GATHERERS.items()
    }
    planners: dict[str, Planner] = {
        subject: LlmPlanner(llm, registry, fallback=p, memory=memory)
        for subject, p in PLANNERS.items()
    }
    return build_court_service(
        Settings(force_all_mock=True, db_url=db_url, dry_run_default=True),
        gatherers=gatherers,
        planners=planners,
        registry=registry,
    )


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return f"{tmp_path.as_posix()}/court.db"


def test_full_agentic_chain_and_precedent_citation(db_path: str) -> None:
    llm = _ScriptedLLM([_GATHER_OK, _PLAN_OK, _GATHER_OK, _PLAN_OK])
    service = _agentic_service(db_path, llm)

    # Trial 1: the agentic evidence and the drafted plan flow into the trial and the audit.
    first = service.submit_change(_REQ)
    trial = service.get_trial(first.thread_id)
    assert trial is not None and trial.impact is not None
    kinds = {(i.system, i.kind) for i in trial.impact.items}
    assert ("crm", "agentic") in kinds  # the Prosecutor's selected read executed
    assert ("prosecutor", "assessment") in kinds
    assert trial.impact.tags  # deterministic core tags intact
    assert trial.options is not None
    assert trial.options.rationale == "drafted by the defender"

    cast = service.cast_verdict(first.thread_id, VerdictType.APPROVE)
    assert cast.execution_status == "done" and cast.audit_id is not None
    audit = service.get_audit(cast.audit_id)
    assert audit is not None
    assert audit.trial.options is not None
    assert audit.trial.options.rationale == "drafted by the defender"

    # Trial 2: both agentic prompts cite the first ruling as precedent.
    service.submit_change(_REQ)
    gather_prompt, _ = llm.prompts[2]
    plan_prompt, _ = llm.prompts[3]
    assert "Past rulings" in gather_prompt
    assert "Past rulings" in plan_prompt
    assert first.thread_id[:8] in gather_prompt  # the citation names the precedent


def test_hallucinated_selections_are_contained_mid_chain(db_path: str) -> None:
    llm = _ScriptedLLM([_GATHER_HALLUCINATED, _PLAN_HALLUCINATED])
    service = _agentic_service(db_path, llm)

    summary = service.submit_change(_REQ)
    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.impact is not None

    # The hallucinated read was rejected, recorded, and the trial carried on.
    assert all(i.kind != "agentic" for i in trial.impact.items)
    # The hallucinated plan fell back whole to the deterministic baseline.
    assert trial.options is not None
    assert trial.options.rationale != "bad"
    assert any(
        s.capability.name == "github.update_milestone_due" for s in trial.options.steps
    )

    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    assert cast.execution_status == "done"  # governance completed despite the hostile LLM output
