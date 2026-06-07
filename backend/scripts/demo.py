"""Run the demo trials end-to-end, fully mocked, and print each Change Court.

The demo driver: ``cd backend && uv run python -m scripts.demo``. No credentials needed
(FORCE_ALL_MOCK). It opens on the *refusal* (a reschedule onto an occupied day — the agent saying
"no" and proposing a free one), then the feasible reschedule, then the two requester-authority
flows — printing each court (decisive evidence, risk, plan) and its verdict.
"""

from __future__ import annotations

import sys

from app.config import Settings
from app.container import build_court_service
from app.domain import ChangeStatus, PlanKind, TrialRecord, VerdictType
from app.services.court_service import CourtService
from app.services.dto import TrialSummary

# Demo order leads with the refusal — the agent saying "no" is the killer moment.
_TRIALS = [
    (
        "Reschedule — conflicting date",
        "move the rehearsal to 2026-06-16",
        VerdictType.ACCEPT_ALTERNATIVE,
    ),
    ("Reschedule — feasible", "move the rehearsal to 2026-06-17", VerdictType.APPROVE),
    ("Meeting Actions", "create action items from standup", VerdictType.APPROVE),
    ("Weekly Report", "post the Project X weekly report", VerdictType.APPROVE),
]


def _print_court(summary: TrialSummary, trial: TrialRecord) -> None:
    print(f"  status={summary.status}  risk={summary.risk_level}  unsafe={summary.unsafe}")
    if summary.unsafe:
        print("  ⛔ REJECTED as requested → proposing a safer alternative")
    if trial.impact is not None:
        for item in (i for i in trial.impact.items if i.severity == "high"):
            print(f"  ‼ decisive: [{item.system}] {item.summary}")
            for fact in item.grounded:
                print(f"      ↳ {fact.claim} ({fact.citation})")
    print(f"  plan: {summary.plan_kind}")
    if trial.options is not None:
        print(f"    rationale: {trial.options.rationale}")
        for step in trial.options.steps:
            print(f"    - {step.capability.name}")
    if trial.quorum is not None:
        approvers = ", ".join(a.role.value for a in trial.quorum.required_approvers)
        print(f"  approvers: {approvers}")
    print(f"  verdict options: {summary.verdict_options}")


def run() -> None:
    # The court text uses a few unicode glyphs; force UTF-8 so it never crashes on a legacy console.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

    service: CourtService = build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )
    for name, request, verdict_type in _TRIALS:
        print(f"\n=== {name} ===\n  > {request}")
        summary = service.submit_change(request)
        trial = service.get_trial(summary.thread_id)
        assert trial is not None
        _print_court(summary, trial)

        if summary.status != ChangeStatus.AWAITING_VERDICT.value:
            # Low risk, no approver: the court auto-approved and executed on submission.
            print(f"  -> executed on the requester's authority: status={summary.status}")
            continue
        selected = (
            PlanKind.SAFE_ALTERNATIVE
            if summary.plan_kind == PlanKind.SAFE_ALTERNATIVE.value
            else PlanKind.FEASIBLE
        )
        cast = service.cast_verdict(summary.thread_id, verdict_type, selected_plan=selected)
        print(
            f"  -> verdict {verdict_type.value}: status={cast.execution_status}"
            f"  audit={cast.audit_id}"
        )


if __name__ == "__main__":
    run()
