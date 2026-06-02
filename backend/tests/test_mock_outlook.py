"""The mock Outlook adapter grounds the Customer Promise trial: review date + email draft."""

from __future__ import annotations

from app.adapters.integrations.mock_outlook import MockOutlookAdapter
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus
from app.ports.integration import ReadQuery


def test_security_review_lands_after_a_mid_june_promise() -> None:
    adapter = MockOutlookAdapter()
    result = adapter.read(
        ReadQuery(capability="outlook.read_security_review", params={"subject": "SSO"})
    )
    assert result.data["review_date"] == "2026-06-18"


def test_email_is_drafted_never_sent() -> None:
    adapter = MockOutlookAdapter()
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="outlook", name="outlook.draft_email"),
        params={"to": "customer@example.com", "subject": "SSO timeline"},
    )
    result = adapter.execute(step, RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert result.after is not None
    draft = result.after["draft"]
    assert isinstance(draft, dict) and draft["sent"] is False


def test_dry_run_creates_no_draft() -> None:
    adapter = MockOutlookAdapter()
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="outlook", name="outlook.draft_email"),
        params={"to": "c@example.com", "subject": "x"},
    )
    result = adapter.execute(step, RunMode.DRY_RUN)
    assert result.status is StepStatus.DRY_RUN
    # no draft was recorded
    again = adapter.execute(step, RunMode.DRY_RUN)
    assert again.before == {"drafts": 0}
