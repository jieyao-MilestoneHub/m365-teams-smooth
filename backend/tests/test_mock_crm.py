"""The mock CRM adapter reports a material renewal value and appends notes."""

from __future__ import annotations

from app.adapters.integrations.mock_crm import MockCRMAdapter
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus
from app.ports.integration import ReadQuery


def test_account_renewal_value_is_material() -> None:
    adapter = MockCRMAdapter()
    data = adapter.read(
        ReadQuery(capability="crm.read_account", params={"account": "Customer A"})
    ).data
    assert data["renewal_value"] == 250000
    assert data["renewal_date"] == "2026-09-30"


def test_unknown_account_has_zero_value() -> None:
    adapter = MockCRMAdapter()
    data = adapter.read(
        ReadQuery(capability="crm.read_account", params={"account": "Nobody"})
    ).data
    assert data["renewal_value"] == 0


def test_add_note_live() -> None:
    adapter = MockCRMAdapter()
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="crm", name="crm.add_note"),
        params={"account": "Customer A", "note": "Do not promise GA; offer private preview."},
    )
    result = adapter.execute(step, RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert result.after is not None and "note" in result.after
