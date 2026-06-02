"""Run the three trials end-to-end, fully mocked, and print each Change Court.

The demo driver: ``cd backend && uv run python -m scripts.demo``. No credentials needed
(FORCE_ALL_MOCK). It submits each request, prints the produced court (impact, risk, plan or safe
alternative, approvers), casts the appropriate verdict, and prints the outcome.
"""

from __future__ import annotations

from app.config import Settings
from app.container import build_court_service
from app.domain import PlanKind, TrialRecord, VerdictType
from app.services.court_service import CourtService
from app.services.dto import TrialSummary

_TRIALS = [
    ("Launch Slip", "slip the launch from 2026-06-10 to 2026-06-17", VerdictType.APPROVE),
    (
        "Customer Promise",
        "promise Customer A that SSO is GA by 2026-06-17",
        VerdictType.ACCEPT_ALTERNATIVE,
    ),
    (
        "Vendor Access",
        "give the vendor access to Project X until the campaign is done",
        VerdictType.ACCEPT_ALTERNATIVE,
    ),
]


def _print_court(summary: TrialSummary, trial: TrialRecord) -> None:
    print(f"  status={summary.status}  risk={summary.risk_level}  unsafe={summary.unsafe}")
    print(f"  plan: {summary.plan_kind}")
    if trial.options is not None:
        print(f"    rationale: {trial.options.rationale}")
        for step in trial.options.steps:
            print(f"    - {step.capability.name}")
    if trial.impact is not None:
        for item in trial.impact.items:
            for fact in item.grounded:
                print(f"    grounded: {fact.claim} ({fact.citation})")
    if trial.quorum is not None:
        approvers = ", ".join(a.role.value for a in trial.quorum.required_approvers)
        print(f"  approvers: {approvers}")
    print(f"  verdict options: {summary.verdict_options}")


def run() -> None:
    service: CourtService = build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )
    for name, request, verdict_type in _TRIALS:
        print(f"\n=== {name} ===\n  > {request}")
        summary = service.submit_change(request)
        trial = service.get_trial(summary.thread_id)
        assert trial is not None
        _print_court(summary, trial)

        selected = (
            PlanKind.SAFE_ALTERNATIVE
            if summary.plan_kind == PlanKind.SAFE_ALTERNATIVE.value
            else PlanKind.FEASIBLE
        )
        cast = service.cast_verdict(summary.thread_id, verdict_type, selected_plan=selected)
        print(f"  -> verdict {verdict_type.value}: status={cast.status}  audit={cast.audit_id}")


if __name__ == "__main__":
    run()
