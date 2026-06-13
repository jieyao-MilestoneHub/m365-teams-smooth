"""The per-scenario harness verifies every demo scenario, isolated, against the golden outcome."""

from __future__ import annotations

import pytest

from scripts.demo_scenario import SCENARIOS, Scenario, _one, _run


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.key)
def test_each_scenario_matches_its_golden_outcome(scenario: Scenario) -> None:
    # Credential-free: every scenario runs analysis-only in a fresh mock service, so each is
    # isolated by construction — one scenario can never mutate state another reads.
    assert _one(scenario, do_reset=False, do_verify=True, force_mock=True) is True


def test_scenarios_run_independently_in_any_order() -> None:
    # Running one scenario must not change another's outcome: a fresh service + analysis-only
    # means no shared mutable state leaks between runs.
    breach = next(s for s in SCENARIOS if s.key == "launch_sla_breach")
    routine = next(s for s in SCENARIOS if s.key == "meeting_actions")

    first = _run(breach, force_mock=True)
    second = _run(routine, force_mock=True)
    breach_again = _run(breach, force_mock=True)

    assert first == breach_again  # the routine run in between changed nothing
    assert second["approvers"] == set()  # routine carries no approver
    assert first["unsafe"] is True and second["unsafe"] is False
