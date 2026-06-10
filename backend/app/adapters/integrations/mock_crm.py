"""Mock CRM adapter: read an account's renewal value/date and contract terms, and append notes.

The seeded account carries a material renewal value, so the Customer Promise trial can weigh the
commercial stake (renewal-at-risk) when a commitment would be unsafe. It also carries a
launch-readiness SLA clause, so a launch-date change can be cross-checked against a contractual
commitment a human reading only the calendar would never see.
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

_SYSTEM = "crm"

_ACCOUNTS: dict[str, dict[str, object]] = {
    "customer a": {
        "renewal_value": 250000,
        "renewal_date": "2026-09-30",
        "currency": "USD",
        # Contractual launch-readiness clause: the rehearsal must complete on or before the SLA
        # date (five business days before the contractual go-live). Read by crm.read_contract.
        "contract": {
            "clause_id": "LR-3",
            "launch_readiness_sla": "2026-06-21",
            "contractual_go_live": "2026-06-26",
        },
    },
}


class MockCRMAdapter(BaseIntegrationAdapter):
    """In-memory CRM stand-in."""

    def __init__(self) -> None:
        self._notes: list[dict[str, object]] = []

    @property
    def system(self) -> str:
        return _SYSTEM

    def _capabilities(self) -> list[Capability]:
        return [
            Capability(system=_SYSTEM, name="crm.read_account", kind=CapabilityKind.READ),
            Capability(system=_SYSTEM, name="crm.read_contract", kind=CapabilityKind.READ),
            Capability(
                system=_SYSTEM,
                name="crm.add_note",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["account", "note"]},
            ),
        ]

    def _read(self, query: ReadQuery) -> ReadResult:
        if query.capability == "crm.read_account":
            account = str(query.params.get("account", "")).lower()
            record = _ACCOUNTS.get(account, {"renewal_value": 0, "renewal_date": None})
            # The contract block is a separate read; don't leak it into the account summary.
            summary = {k: v for k, v in record.items() if k != "contract"}
            return ReadResult(capability=query.capability, data={"account": account, **summary})
        if query.capability == "crm.read_contract":
            account = str(query.params.get("account", "")).lower()
            record = _ACCOUNTS.get(account, {})
            contract = record.get("contract", {}) if isinstance(record, dict) else {}
            data = dict(contract) if isinstance(contract, dict) else {}
            return ReadResult(capability=query.capability, data={"account": account, **data})
        raise IntegrationError(f"{_SYSTEM}: unknown read capability '{query.capability}'")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        return PredictedEffect(summary="would add an account note", diff=dict(step.params))

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        note = dict(step.params)
        self._notes.append(note)
        return {"note": note}

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return {"notes": len(self._notes)}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction="remove the appended account note",
            params=dict(step.params),
        )
