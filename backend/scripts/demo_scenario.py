"""Per-scenario demo prep + verify: seed one scenario's data, run it isolated, check the result.

Each demo scenario is verifiable on its own, with no contamination from another scenario's run:

- **Isolation by construction.** Every scenario runs in ``run_mode=ANALYZE`` against a fresh
  ``CourtService`` with an in-memory database. Analysis-only never executes, so it never writes to
  any system — one scenario can never mutate state another reads. Mock adapters are constructed
  fresh per service, so their in-memory fixtures start clean every time.
- **Real read-side, canonical.** ``--reset`` restores the live read-side a scenario depends on
  (the GitHub milestone + ticket, the seeded Outlook calendar, the SharePoint freeze calendar) to
  its seeded state, in case an earlier *live* execution moved it. Only the systems a scenario
  actually reads are reseeded, and only when their credentials are present.
- **A verifiable oracle.** ``--verify`` asserts the scenario's risk, safety, plan kind, plan steps,
  and required approvers against the golden values — the same table the test suite pins.

The headline reschedule runs against real GitHub/Outlook/SharePoint when their credentials are in
the environment; the four additional capabilities are fixture-driven (CRM, Planner, Teams notes are
mock-only) and always verify under mocks so their outcome is reproducible.

Run (from ``backend/``):
    uv run python -m scripts.demo_scenario --list
    uv run python -m scripts.demo_scenario --scenario launch_sla_breach --reset --verify
    uv run python -m scripts.demo_scenario --all --verify            # every scenario, isolated
    uv run python -m scripts.demo_scenario --all --reset --verify    # reset the read-side first
    uv run python -m scripts.demo_scenario --all --verify --mock     # force credential-free check
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field

from app.config import Settings
from app.container import build_court_service
from app.domain import RunMode
from scripts import seed_calendar, seed_github, seed_sharepoint
from scripts.demo_identities import DIRECTORY, REQUESTER

# Seed modules keyed by the name a scenario references; each exposes audit()/apply().
_SEEDS = {"github": seed_github, "calendar": seed_calendar, "sharepoint": seed_sharepoint}


@dataclass(frozen=True)
class Scenario:
    """A demo scenario with its golden outcome and the live read-side it depends on."""

    key: str
    request: str
    risk_level: str
    unsafe: bool
    plan_kind: str
    approvers: frozenset[str]
    plan_capabilities: frozenset[str]
    # The seeded live systems whose mutable state this scenario reads (reseeded by --reset).
    reset_systems: tuple[str, ...] = ()
    # True when the outcome is driven by mock-only fixtures (CRM/Planner/Teams) — always verified
    # under mocks so it stays reproducible regardless of what the real systems hold.
    fixture_only: bool = False
    note: str = field(default="")


# The golden table the test suite pins (tests/test_golden_trials.py), expressed per demo scenario.
SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        key="launch_sla_breach",
        request="move the launch rehearsal to 2026-06-22",
        risk_level="high",
        unsafe=True,
        plan_kind="safe_alternative",
        approvers=frozenset({"eng_lead", "comms", "account_owner"}),
        plan_capabilities=frozenset(
            {
                "github.update_milestone_due",
                "outlook.create_event",
                "planner.shift_task_dates",
                "teams.update_announcement",
            }
        ),
        reset_systems=("github", "calendar", "sharepoint"),
        note="the headline — a free day that breaches the SLA, freeze, and go-live buffer at once",
    ),
    Scenario(
        key="rehearsal_conflict",
        request="move the rehearsal to 2026-06-16",
        risk_level="high",
        unsafe=True,
        plan_kind="safe_alternative",
        approvers=frozenset({"eng_lead", "comms"}),
        plan_capabilities=frozenset(
            {
                "github.update_milestone_due",
                "outlook.create_event",
                "planner.shift_task_dates",
                "teams.update_announcement",
            }
        ),
        reset_systems=("github", "calendar"),
        note="collides visibly with the seeded Board review; the next free day is proposed",
    ),
    Scenario(
        key="meeting_actions",
        request="create action items from standup",
        risk_level="low",
        unsafe=False,
        plan_kind="feasible",
        approvers=frozenset(),
        plan_capabilities=frozenset({"planner.create_task", "outlook.create_event"}),
        fixture_only=True,
        note="routine — the requester's own authority, no approver added",
    ),
    Scenario(
        key="weekly_report",
        request="post the Project X weekly report",
        risk_level="low",
        unsafe=False,
        plan_kind="feasible",
        approvers=frozenset(),
        plan_capabilities=frozenset({"teams.post_message"}),
        fixture_only=True,
        note="routine — the requester's own authority, no approver added",
    ),
    Scenario(
        key="customer_promise",
        request="promise Customer A that SSO is GA by 2026-06-17",
        risk_level="high",
        unsafe=True,
        plan_kind="safe_alternative",
        approvers=frozenset({"security_lead", "account_owner"}),
        plan_capabilities=frozenset(
            {
                "github.comment_issue",
                "outlook.create_event",
                "crm.add_note",
                "outlook.draft_email",
                "teams.create_escalation_thread",
            }
        ),
        fixture_only=True,
        note="unsafe GA promise refused; a private preview with gated GA proposed",
    ),
    Scenario(
        key="vendor_access",
        request="give the vendor access to Project X until the campaign is done",
        risk_level="high",
        unsafe=True,
        plan_kind="safe_alternative",
        approvers=frozenset({"manager", "security_lead"}),
        plan_capabilities=frozenset(
            {
                "sharepoint.grant_folder_permission",
                "entra.invite_guest",
                "entra.schedule_access_revoke",
            }
        ),
        reset_systems=("sharepoint",),
        note="over-broad, undated access narrowed to least-privilege and time-boxed",
    ),
)

_BY_KEY = {s.key: s for s in SCENARIOS}


def _real_credentials_present() -> bool:
    """True when at least GitHub real-mode credentials are configured (headline read path)."""
    return bool(os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPO"))


def _reset(scenario: Scenario) -> None:
    """Restore the seeded read-side a scenario depends on; skip systems without credentials."""
    if scenario.fixture_only or not scenario.reset_systems:
        print("  reset: nothing to restore (fixture-driven; mock data is fresh each run)")
        return
    for name in scenario.reset_systems:
        seed = _SEEDS[name]
        if not seed.audit().get("ready"):
            print(f"  reset: {name} skipped (no credentials)")
            continue
        seed.apply()
        print(f"  reset: {name} restored to seeded state")


def _run(scenario: Scenario, *, force_mock: bool) -> dict[str, object]:
    """Run one scenario analysis-only in a fresh service; return its observed outcome."""
    use_mock = force_mock or scenario.fixture_only or not _real_credentials_present()
    service = build_court_service(
        Settings(
            force_all_mock=use_mock,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            approver_directory=DIRECTORY,
        )
    )
    summary = service.submit_change(
        scenario.request, run_mode=RunMode.ANALYZE, requester=REQUESTER
    )
    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.options is not None and trial.quorum is not None
    return {
        "mode": "mock" if use_mock else "real",
        "risk_level": summary.risk_level,
        "unsafe": summary.unsafe,
        "plan_kind": summary.plan_kind,
        "approvers": {a.role.value for a in trial.quorum.required_approvers},
        "plan_capabilities": {s.capability.name for s in trial.options.steps},
    }


def _verify(scenario: Scenario, observed: dict[str, object]) -> list[str]:
    """Compare an observed outcome against the golden values; return a list of mismatches."""
    checks = {
        "risk_level": scenario.risk_level,
        "unsafe": scenario.unsafe,
        "plan_kind": scenario.plan_kind,
        "approvers": set(scenario.approvers),
        "plan_capabilities": set(scenario.plan_capabilities),
    }
    failures = []
    for field_name, expected in checks.items():
        actual = observed[field_name]
        if actual != expected:
            failures.append(f"{field_name}: expected {expected!r}, got {actual!r}")
    return failures


def _one(scenario: Scenario, *, do_reset: bool, do_verify: bool, force_mock: bool) -> bool:
    print(f"\n=== {scenario.key} ===\n  > {scenario.request}\n  ({scenario.note})")
    if do_reset:
        _reset(scenario)
    observed = _run(scenario, force_mock=force_mock)
    gate = "would need approval" if observed["approvers"] else "no approver"
    print(
        f"  mode={observed['mode']}  risk={observed['risk_level']}  "
        f"unsafe={observed['unsafe']}  plan={observed['plan_kind']}  {gate}"
    )
    if not do_verify:
        return True
    failures = _verify(scenario, observed)
    if failures:
        print("  FAIL")
        for line in failures:
            print(f"    - {line}")
        return False
    print("  PASS — matches the golden outcome")
    return True


def main() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Per-scenario demo prep + verify (isolated, contamination-free)."
    )
    parser.add_argument("--scenario", choices=list(_BY_KEY), help="run a single scenario")
    parser.add_argument("--all", action="store_true", help="run every scenario, each isolated")
    parser.add_argument("--list", action="store_true", help="list the scenarios and exit")
    parser.add_argument(
        "--reset", action="store_true", help="restore each scenario's seeded read-side first"
    )
    parser.add_argument(
        "--verify", action="store_true", help="assert each outcome against the golden values"
    )
    parser.add_argument(
        "--mock", action="store_true", help="force credential-free mocks for every scenario"
    )
    args = parser.parse_args()

    if args.list or not (args.scenario or args.all):
        print("Scenarios:")
        for s in SCENARIOS:
            surface = "fixture" if s.fixture_only else "real-capable"
            print(f"  {s.key:<20} [{surface}]  {s.request}")
        if not args.list:
            print("\nPass --scenario <key> or --all (add --reset and/or --verify).")
        return

    chosen = SCENARIOS if args.all else (_BY_KEY[args.scenario],)
    results = [
        _one(s, do_reset=args.reset, do_verify=args.verify, force_mock=args.mock) for s in chosen
    ]
    if args.verify:
        passed = sum(results)
        print(f"\n{passed}/{len(results)} scenario(s) match the golden outcome.")
        if passed != len(results):
            sys.exit(1)


if __name__ == "__main__":
    main()
