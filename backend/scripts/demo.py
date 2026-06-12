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
from app.domain import ChangeStatus, TrialRecord
from app.services.court_service import CourtService
from app.services.dto import TrialSummary
from scripts.demo_identities import APPROVER, DIRECTORY, REQUESTER

# The headline leads with the refusal — the agent saying "no" is the killer moment — then shows the
# same machinery cleanly approving a safe date. The first trial is the deepest: a date that is free
# on the calendar yet breaches a contract SLA, a release freeze, and a go-live buffer at once — a
# latent conflict no single system reveals, which the court catches by cross-referencing three.
_HEADLINE = [
    ("Reschedule — hidden contractual breach", "move the launch rehearsal to 2026-06-22"),
    ("Reschedule — conflicting date", "move the rehearsal to 2026-06-16"),
    ("Reschedule — feasible", "move the rehearsal to 2026-06-17"),
]

# Additional capabilities the same engine handles — runnable with --all, not part of the recording.
_ADDITIONAL = [
    ("Meeting Actions", "create action items from standup"),
    ("Weekly Report", "post the Project X weekly report"),
    ("Customer Promise", "promise Customer A that SSO is GA by 2026-06-17"),
    ("Vendor Access", "give the vendor access to Project X until the campaign is done"),
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
    if trial.deliberation is not None:
        print("  🧠 reasoning:")
        for e in trial.deliberation.entries:
            who = f"{e.node}/{e.role}" if e.role else e.node
            print(f"      [{who}] {e.rationale} ({e.source})")
    print(f"  verdict options: {summary.verdict_options}")


def run(*, include_additional: bool = False) -> None:
    # The court text uses a few unicode glyphs; force UTF-8 so it never crashes on a legacy console.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

    trials = _HEADLINE + _ADDITIONAL if include_additional else _HEADLINE
    service: CourtService = build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            approver_directory=DIRECTORY,
        )
    )
    for name, request in trials:
        print(f"\n=== {name} ===\n  > {request}")
        summary = service.submit_change(request, requester=REQUESTER)
        trial = service.get_trial(summary.thread_id)
        assert trial is not None
        _print_court(summary, trial)

        # The requester reviews their own proposal and sends it on; a no-approver change
        # executes right here, on their confirmation.
        summary = service.send_for_approval(
            summary.thread_id, actor=REQUESTER, note="please review — the evidence is attached"
        )
        if summary.status != ChangeStatus.AWAITING_APPROVAL.value:
            print(f"  -> executed on the requester's confirmation: status={summary.status}")
            continue
        # The quorum's authorized approver decides on the evidence; for an unsafe request the
        # approval adopts the safe alternative the court proposed.
        decided = service.decide(
            summary.thread_id, actor=APPROVER, approve=True, note="approved on the evidence"
        )
        print(f"  -> decided by {APPROVER.display_name}: status={decided.status}")


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
