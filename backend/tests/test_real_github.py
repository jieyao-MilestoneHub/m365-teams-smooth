"""The real GitHub adapter over recorded HTTP: reads, a write, dry-run, error containment."""

from __future__ import annotations

import httpx
import respx

from app.adapters.integrations.real_github import RealGitHubAdapter
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus
from app.ports.integration import ReadQuery

_API = "https://api.github.com"


def _adapter() -> RealGitHubAdapter:
    return RealGitHubAdapter("test-token", "octo/launch")


def _update_step() -> ExecutionStep:
    return ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="github", name="github.update_milestone_due"),
        params={"milestone": "Launch", "due_on": "2026-06-17T00:00:00Z"},
    )


@respx.mock
def test_read_milestone() -> None:
    respx.get(f"{_API}/repos/octo/launch/milestones").mock(
        return_value=httpx.Response(
            200, json=[{"title": "Launch", "due_on": "2026-06-10T00:00:00Z", "number": 1}]
        )
    )
    data = _adapter().read(
        ReadQuery(capability="github.read_milestone", params={"milestone": "Launch"})
    ).data
    assert data["due_on"] == "2026-06-10T00:00:00Z"


@respx.mock
def test_read_blocking_issues() -> None:
    respx.get(f"{_API}/repos/octo/launch/issues").mock(
        return_value=httpx.Response(200, json=[{"number": 42, "title": "blocker", "state": "open"}])
    )
    data = _adapter().read(ReadQuery(capability="github.read_blocking_issues")).data
    assert isinstance(data["issues"], list) and data["issues"][0]["number"] == 42


@respx.mock
def test_read_blocking_issues_excludes_prs_and_normalizes() -> None:
    # The /issues endpoint returns pull requests too; they must not be counted as blockers, and
    # only the {number, title, state} fields should survive into the evidence.
    respx.get(f"{_API}/repos/octo/launch/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"number": 42, "title": "SSO blocker", "state": "open", "body": "secret details"},
                {"number": 43, "title": "a PR", "state": "open", "pull_request": {"url": "..."}},
            ],
        )
    )
    data = _adapter().read(ReadQuery(capability="github.read_blocking_issues")).data
    assert data["issues"] == [{"number": 42, "title": "SSO blocker", "state": "open"}]


@respx.mock
def test_live_update_milestone_due() -> None:
    respx.get(f"{_API}/repos/octo/launch/milestones").mock(
        return_value=httpx.Response(
            200, json=[{"title": "Launch", "due_on": "2026-06-10T00:00:00Z", "number": 1}]
        )
    )
    patch = respx.patch(f"{_API}/repos/octo/launch/milestones/1").mock(
        return_value=httpx.Response(200, json={"title": "Launch", "due_on": "2026-06-17T00:00:00Z"})
    )
    result = _adapter().execute(_update_step(), RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert patch.called


@respx.mock
def test_dry_run_reads_before_but_makes_no_write_call() -> None:
    # fetch_before reads the current milestone even in dry-run; only the write (PATCH) is withheld.
    respx.get(f"{_API}/repos/octo/launch/milestones").mock(
        return_value=httpx.Response(
            200, json=[{"title": "Launch", "due_on": "2026-06-10T00:00:00Z", "number": 1}]
        )
    )
    patch = respx.patch(f"{_API}/repos/octo/launch/milestones/1").mock(
        return_value=httpx.Response(200, json={})
    )
    result = _adapter().execute(_update_step(), RunMode.DRY_RUN)
    assert result.status is StepStatus.DRY_RUN
    assert not patch.called  # dry-run never mutates


@respx.mock
def test_http_error_is_contained_as_failed() -> None:
    respx.post(f"{_API}/repos/octo/launch/issues").mock(return_value=httpx.Response(404))
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="github", name="github.create_issue"),
        params={"title": "x"},
    )
    result = _adapter().execute(step, RunMode.LIVE)  # must not raise
    assert result.status is StepStatus.FAILED
    assert result.error is not None


def test_injected_repo_param_is_rejected_before_any_call() -> None:
    # A planner/LLM-supplied traversal in the repo param must never reach the API.
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="github", name="github.update_milestone_due"),
        params={"milestone": "Launch", "due_on": "2026-06-17", "repo": "../victim/repo"},
    )
    result = _adapter().execute(step, RunMode.LIVE)
    assert result.status is StepStatus.FAILED
    assert result.error is not None and "invalid repository" in result.error
