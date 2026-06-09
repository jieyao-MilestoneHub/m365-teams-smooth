"""Run the Change Court demo end-to-end, fully mocked, and print each Change Court.

The demo driver: ``cd backend && uv run python -m scripts.demo``. No credentials needed
(FORCE_ALL_MOCK). By default it runs only the **headline — Informed Approval**: a reschedule onto an
occupied day (the agent saying "no" and proposing a free one), then the feasible reschedule — the
one scenario worth recording. Pass ``--all`` to also tour the additional capabilities the same
engine already handles (Meeting Actions, Weekly Report, Customer Promise, Vendor Access) — not part
of the headline, there to be played with. Each court prints its evidence, risk, plan, and verdict.
"""

from __future__ import annotations

import argparse
import sys

from app.config import Settings
from app.container import build_court_service
from app.domain import ChangeStatus, PlanKind, TrialRecord, VerdictType
from app.services.court_service import CourtService
from app.services.dto import TrialSummary

# The headline leads with the refusal — the agent saying "no" is the killer moment — then shows the
# same machinery cleanly approving a safe date.
_HEADLINE = [
    (
        "Reschedule — conflicting date",
        "move the rehearsal to 2026-06-16",
        VerdictType.ACCEPT_ALTERNATIVE,
    ),
    ("Reschedule — feasible", "move the rehearsal to 2026-06-17", VerdictType.APPROVE),
]

# Additional capabilities the same engine handles — runnable with --all, not part of the recording.
_ADDITIONAL = [
    ("Meeting Actions", "create action items from standup", VerdictType.APPROVE),
    ("Weekly Report", "post the Project X weekly report", VerdictType.APPROVE),
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


def run(*, include_additional: bool = False) -> None:
    # The court text uses a few unicode glyphs; force UTF-8 so it never crashes on a legacy console.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

    trials = _HEADLINE + _ADDITIONAL if include_additional else _HEADLINE
    service: CourtService = build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )
    for name, request, verdict_type in trials:
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
    parser = argparse.ArgumentParser(description="Run the Change Court demo (headline by default).")
    parser.add_argument(
        "--all",
        dest="include_additional",
        action="store_true",
        help="also run the additional capabilities (Meeting Actions, Weekly Report, "
        "Customer Promise, Vendor Access)",
    )
    run(include_additional=parser.parse_args().include_additional)
