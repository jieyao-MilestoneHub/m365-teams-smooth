"""Evidence webhook notifier: pushes the trial's evidence packet to an external endpoint.

Where the Teams channels notify *people*, this channel notifies a *system*: each approval event
POSTs a JSON evidence packet — the change, the cross-system impact evidence with citations, the
risk factors, the proposed plan or safe alternative, the quorum, and the signed run-page link —
to a configured webhook URL, so an existing ticket or change-management workflow can attach the
analysis its approver is missing. It composes presentation only: trial data comes from an
injected reader, the run link from an injected generator, delivery is one bounded POST. Failures
raise per the port contract; callers treat notification failure as non-fatal.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from app.domain import TrialRecord
from app.ports.notifier import ApprovalNotifier

TrialReader = Callable[[str], TrialRecord | None]
RunLink = Callable[[str], str | None]

# Mirrors the state-level evidence cap; re-applied here so the packet stays bounded even if an
# upstream record carries more.
_MAX_PACKET_ITEMS = 30


class EvidenceWebhookNotifier(ApprovalNotifier):
    """POSTs one evidence packet per approval event to the configured webhook URL."""

    def __init__(
        self,
        *,
        url: str,
        trial_reader: TrialReader,
        run_link: RunLink,
        token: str = "",
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._url = url
        self._trial_reader = trial_reader
        self._run_link = run_link
        self._token = token
        self._client = client or httpx.Client(timeout=timeout)

    def approval_requested(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
        note: str,
    ) -> None:
        self._post(
            "approval_requested",
            thread_id,
            {
                "title": title,
                "requester": requester_upn,
                "approvers": approver_upns,
                "note": note,
            },
        )

    def decided(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approved: bool,
        decider_upn: str,
        note: str,
    ) -> None:
        self._post(
            "decided",
            thread_id,
            {
                "title": title,
                "requester": requester_upn,
                "approved": approved,
                "decider": decider_upn,
                "note": note,
            },
        )

    def acknowledged(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
    ) -> None:
        self._post(
            "acknowledged",
            thread_id,
            {"title": title, "requester": requester_upn, "approvers": approver_upns},
        )

    def _post(self, event: str, thread_id: str, fields: dict[str, object]) -> None:
        payload: dict[str, object] = {"event": event, "thread_id": thread_id, **fields}
        payload.update(self._packet(thread_id))
        run_url = self._run_link(thread_id)
        if run_url:
            payload["run_url"] = run_url
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        response = self._client.post(self._url, json=payload, headers=headers)
        response.raise_for_status()

    def _packet(self, thread_id: str) -> dict[str, object]:
        """The trial-derived sections of the payload; empty when the trial is unreadable."""
        trial = self._trial_reader(thread_id)
        if trial is None:
            return {}
        packet: dict[str, object] = {
            "change": {
                "raw_request": trial.change.raw_request,
                "subject": trial.change.subject,
                "unsafe": trial.change.unsafe,
                "unsafe_reason": trial.change.unsafe_reason,
                "requester": trial.change.requester.upn if trial.change.requester else None,
            }
        }
        if trial.risk is not None:
            packet["risk"] = {
                "level": trial.risk.level.value,
                "score": trial.risk.score,
                "requires_approval": trial.risk.requires_approval,
                "factors": [
                    {
                        "id": factor.id,
                        "label": factor.label,
                        "weight": factor.weight,
                        "evidence_tag": factor.evidence_tag,
                        "citations": factor.grounded_citations,
                    }
                    for factor in trial.risk.factors
                ],
            }
        if trial.impact is not None:
            packet["impact"] = {
                "tags": trial.impact.tags,
                "items": [
                    {
                        "system": item.system,
                        "kind": item.kind,
                        "summary": item.summary,
                        "severity": item.severity,
                        "citations": [fact.citation for fact in item.grounded if fact.citation],
                    }
                    for item in trial.impact.items[:_MAX_PACKET_ITEMS]
                ],
            }
        if trial.options is not None:
            packet["plan"] = {
                "kind": trial.options.kind.value,
                "rationale": trial.options.rationale,
                "supersedes_request": trial.options.supersedes_request,
                "steps": [
                    {
                        "step_id": step.step_id,
                        "system": step.capability.system,
                        "capability": step.capability.name,
                    }
                    for step in trial.options.steps
                ],
            }
        if trial.quorum is not None:
            packet["quorum"] = {
                "policy": trial.quorum.policy,
                "required_roles": [a.role.value for a in trial.quorum.required_approvers],
            }
        if trial.verdict is not None:
            packet["verdict"] = {
                "type": trial.verdict.type.value,
                "actor": trial.verdict.actor,
                "selected_plan": trial.verdict.selected_plan.value,
            }
        if trial.results:
            packet["results"] = [
                {
                    "step_id": result.step_id,
                    "status": result.status.value,
                    "error": result.error,
                    "resource_url": result.resource_url,
                }
                for result in trial.results
            ]
        return packet
