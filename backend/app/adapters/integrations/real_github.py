"""Real GitHub adapter: reads milestones/blockers/dependencies, writes milestone/issue.

Implements the same github capabilities as the mock over the GitHub REST API. The base class owns
the dry-run branch (so DRY_RUN never calls the API) and maps any HTTP/SDK error to IntegrationError;
this adapter only fills the read/predict/apply hooks. Selected when github runs in ``real`` mode.
"""

from __future__ import annotations

import re

import httpx

from app.adapters.integrations.base import BaseIntegrationAdapter
from app.adapters.integrations.retry import RetryPolicy
from app.adapters.integrations.validation import safe_repo
from app.domain import (
    Capability,
    CapabilityKind,
    ExecutionStep,
    PredictedEffect,
    RollbackHint,
)
from app.domain.errors import IntegrationError
from app.ports.integration import ReadQuery, ReadResult

_SYSTEM = "github"
_API = "https://api.github.com"

# GitHub has no native milestone dependencies, so they are declared as data in the dependent
# milestone's description: a "depends_on: <title>" line names the upstream milestone and
# "required_buffer_days: <n>" the gap it needs before its own due date (the mock's data shape).
_DEPENDS_ON = re.compile(r"^\s*depends_on:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_BUFFER_DAYS = re.compile(r"^\s*required_buffer_days:\s*(\d+)\s*$", re.IGNORECASE | re.MULTILINE)


class RealGitHubAdapter(BaseIntegrationAdapter):
    """Talks to the GitHub REST API for one repository."""

    def __init__(
        self,
        token: str,
        repo: str,
        *,
        client: httpx.Client | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        super().__init__(retry=retry)
        self._repo = repo
        self._client = client or httpx.Client(
            base_url=_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10.0,
        )

    @property
    def system(self) -> str:
        return _SYSTEM

    def _repo_of(self, step: ExecutionStep) -> str:
        return safe_repo(str(step.params.get("repo", self._repo)))

    def _get(self, path: str, **params: object) -> httpx.Response:
        response = self._client.get(path, params={k: str(v) for k, v in params.items()})
        response.raise_for_status()
        return response

    def _capabilities(self) -> list[Capability]:
        return [
            Capability(system=_SYSTEM, name="github.read_milestone", kind=CapabilityKind.READ),
            Capability(
                system=_SYSTEM, name="github.read_blocking_issues", kind=CapabilityKind.READ
            ),
            Capability(
                system=_SYSTEM, name="github.read_closed_issues", kind=CapabilityKind.READ
            ),
            Capability(
                system=_SYSTEM, name="github.read_milestone_dependencies", kind=CapabilityKind.READ
            ),
            Capability(
                system=_SYSTEM,
                name="github.update_milestone_due",
                kind=CapabilityKind.WRITE,
                params_schema={
                    "required": ["milestone", "due_on"],
                    "properties": {"due_on": {"format": "date"}},
                },
            ),
            Capability(
                system=_SYSTEM,
                name="github.create_issue",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["title"]},
            ),
            Capability(
                system=_SYSTEM,
                name="github.comment_issue",
                kind=CapabilityKind.WRITE,
                params_schema={
                    "required": ["issue", "body"],
                    "properties": {"issue": {"pattern": "^[0-9]+$"}},
                },
            ),
        ]

    def _find_milestone(self, repo: str, title: str) -> dict[str, object]:
        milestones = self._get(f"/repos/{repo}/milestones", state="all").json()
        for milestone in milestones:
            if milestone.get("title") == title:
                return dict(milestone)
        return {}

    def _read(self, query: ReadQuery) -> ReadResult:
        repo = safe_repo(str(query.params.get("repo", self._repo)))
        if query.capability == "github.read_milestone":
            title = str(query.params.get("milestone", "Launch Rehearsal"))
            found = self._find_milestone(repo, title)
            return ReadResult(
                capability=query.capability,
                data={"title": found.get("title"), "due_on": found.get("due_on")},
            )
        if query.capability == "github.read_blocking_issues":
            label = str(query.params.get("label", "blocker"))
            raw = self._get(f"/repos/{repo}/issues", state="open", labels=label).json()
            # The /issues endpoint also returns pull requests (each carries a "pull_request" key);
            # drop those so PRs aren't counted as blockers, and normalize to the fields the impact
            # evidence needs (raw issue objects are large and would leak into the card and audit).
            issues = [
                {
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "state": item.get("state"),
                }
                for item in raw
                if "pull_request" not in item
            ]
            return ReadResult(capability=query.capability, data={"issues": issues})
        if query.capability == "github.read_closed_issues":
            # ``since`` filters by update time on this endpoint — close enough for a recent-
            # activity report. PRs are dropped and the list capped so evidence stays card-sized.
            params: dict[str, object] = {"state": "closed", "per_page": 30}
            since = str(query.params.get("since", ""))
            if since:
                if len(since) == 10:
                    since = f"{since}T00:00:00Z"
                params["since"] = since
            raw = self._get(f"/repos/{repo}/issues", **params).json()
            issues = [
                {
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "closed_at": item.get("closed_at"),
                }
                for item in raw
                if "pull_request" not in item
            ][:10]
            return ReadResult(capability=query.capability, data={"issues": issues})
        if query.capability == "github.read_milestone_dependencies":
            title = str(query.params.get("milestone", "Launch Rehearsal"))
            milestones = self._get(f"/repos/{repo}/milestones", state="all").json()
            dependents: list[dict[str, object]] = []
            for milestone in milestones:
                description = str(milestone.get("description") or "")
                depends = _DEPENDS_ON.search(description)
                if depends is None or depends.group(1) != title:
                    continue
                dependent: dict[str, object] = {
                    "milestone": milestone.get("title"),
                    "due_on": milestone.get("due_on"),
                    "depends_on": title,
                }
                buffer_days = _BUFFER_DAYS.search(description)
                if buffer_days is not None:
                    dependent["required_buffer_days"] = int(buffer_days.group(1))
                dependents.append(dependent)
            return ReadResult(capability=query.capability, data={"dependents": dependents})
        raise IntegrationError(f"{_SYSTEM}: unknown read capability '{query.capability}'")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        return PredictedEffect(summary=f"would call {step.capability.name}", diff=dict(step.params))

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        repo = self._repo_of(step)
        name = step.capability.name
        if name == "github.update_milestone_due":
            title = str(step.params["milestone"])
            number = self._find_milestone(repo, title).get("number")
            if number is None:
                raise IntegrationError(f"{_SYSTEM}: milestone '{title}' not found")
            due_on = str(step.params["due_on"])
            if len(due_on) == 10:  # plans carry plain dates; the API wants a full timestamp
                due_on = f"{due_on}T00:00:00Z"
            resp = self._client.patch(
                f"/repos/{repo}/milestones/{number}", json={"due_on": due_on}
            )
            resp.raise_for_status()
            return {"milestone": resp.json()}
        if name == "github.create_issue":
            resp = self._client.post(f"/repos/{repo}/issues", json=dict(step.params))
            resp.raise_for_status()
            return {"issue": resp.json()}
        if name == "github.comment_issue":
            issue = step.params["issue"]
            resp = self._client.post(
                f"/repos/{repo}/issues/{issue}/comments", json={"body": step.params["body"]}
            )
            resp.raise_for_status()
            return {"comment": resp.json()}
        raise IntegrationError(f"{_SYSTEM}: unknown write capability '{name}'")

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        if step.capability.name == "github.update_milestone_due":
            repo = self._repo_of(step)
            return self._find_milestone(repo, str(step.params.get("milestone", "Launch Rehearsal")))
        return {}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction="restore the prior milestone due date / close the created issue or comment",
            params=before,
        )
