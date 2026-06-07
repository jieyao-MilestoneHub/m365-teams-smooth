"""Mock GitHub adapter: milestone read/update, blocking-issue read, issue create/comment.

Lets the trials run fully mocked with zero credentials. The real GitHub adapter satisfies the same
capabilities later; this mock is selected whenever github runs in mock mode (or FORCE_ALL_MOCK).
"""

from __future__ import annotations

from app.adapters.integrations.base import BaseIntegrationAdapter
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


class MockGitHubAdapter(BaseIntegrationAdapter):
    """In-memory GitHub stand-in."""

    def __init__(self) -> None:
        self._milestones: dict[str, dict[str, object]] = {
            "Launch Rehearsal": {"title": "Launch Rehearsal", "due_on": "2026-06-10"},
        }
        # Open issues that block SSO going generally available (Customer Promise).
        self._blocking_issues: list[dict[str, object]] = [
            {"number": 42, "title": "SSO: finish SAML edge cases", "state": "open"},
            {"number": 47, "title": "SSO: pen-test findings", "state": "open"},
        ]
        self._created_issues: list[dict[str, object]] = []
        self._comments: list[dict[str, object]] = []
        # Recently closed work — the activity a status report aggregates.
        self._closed_issues: list[dict[str, object]] = [
            {"number": 31, "title": "Fix flaky webhook retries", "closed_at": "2026-06-02"},
            {"number": 35, "title": "Add audit export", "closed_at": "2026-06-03"},
            {"number": 38, "title": "Harden token refresh", "closed_at": "2026-06-05"},
            {"number": 40, "title": "Polish run-page styles", "closed_at": "2026-06-06"},
        ]

    @property
    def system(self) -> str:
        return _SYSTEM

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

    def _read(self, query: ReadQuery) -> ReadResult:
        if query.capability == "github.read_milestone":
            name = str(query.params.get("milestone", "Launch Rehearsal"))
            return ReadResult(
                capability=query.capability, data=dict(self._milestones.get(name, {}))
            )
        if query.capability == "github.read_blocking_issues":
            return ReadResult(
                capability=query.capability, data={"issues": list(self._blocking_issues)}
            )
        if query.capability == "github.read_closed_issues":
            since = str(query.params.get("since", ""))
            issues = [
                dict(i) for i in self._closed_issues if not since or str(i["closed_at"]) >= since
            ]
            return ReadResult(capability=query.capability, data={"issues": issues})
        raise IntegrationError(f"{_SYSTEM}: unknown read capability '{query.capability}'")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        summaries = {
            "github.update_milestone_due": "would move the milestone due date",
            "github.create_issue": "would create an issue",
            "github.comment_issue": "would comment on an issue",
        }
        return PredictedEffect(
            summary=summaries.get(step.capability.name, "would change GitHub"),
            diff=dict(step.params),
        )

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        name = step.capability.name
        if name == "github.update_milestone_due":
            milestone = str(step.params["milestone"])
            record = self._milestones.setdefault(milestone, {"title": milestone})
            record["due_on"] = step.params["due_on"]
            return {"milestone": dict(record)}
        if name == "github.create_issue":
            issue = dict(step.params)
            self._created_issues.append(issue)
            return {"issue": issue}
        if name == "github.comment_issue":
            comment = dict(step.params)
            self._comments.append(comment)
            return {"comment": comment}
        raise IntegrationError(f"{_SYSTEM}: unknown write capability '{name}'")

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        if step.capability.name == "github.update_milestone_due":
            milestone = str(step.params.get("milestone", "Launch Rehearsal"))
            return dict(self._milestones.get(milestone, {}))
        if step.capability.name == "github.create_issue":
            return {"issues": len(self._created_issues)}
        return {"comments": len(self._comments)}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction="restore the prior milestone due date / delete the created issue/comment",
            params=before,
        )
