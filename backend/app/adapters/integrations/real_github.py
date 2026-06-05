"""Real GitHub adapter: the one live integration (read blockers/milestone, write milestone/issue).

Implements the same github capabilities as the mock over the GitHub REST API. The base class owns
the dry-run branch (so DRY_RUN never calls the API) and maps any HTTP/SDK error to IntegrationError;
this adapter only fills the read/predict/apply hooks. Selected when github runs in ``real`` mode.
"""

from __future__ import annotations

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
            title = str(query.params.get("milestone", "Launch"))
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
            return self._find_milestone(repo, str(step.params.get("milestone", "Launch")))
        return {}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction="restore the prior milestone due date / close the created issue or comment",
            params=before,
        )
