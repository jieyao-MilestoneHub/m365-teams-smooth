"""Export the Change Court Adaptive Card JSON, fully mocked.

Run: ``cd backend && uv run python -m scripts.export_cards`` (or ``make cards``). No credentials
(FORCE_ALL_MOCK). By default it exports only the **headline — Informed Approval** cards (the
reschedule conflict refusal and the feasible reschedule); pass ``--all`` to also export the cards
for the additional capabilities the same engine handles. Writes paste-into-Designer-ready card JSON
to ``m365/adaptive-cards/generated/``, so the Change Court card has a real, tenant-free visual —
open a file at https://adaptivecards.io/designer, or run the Playground bot. A thin façade over the
service and the card builders: no business logic here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import Settings
from app.container import build_court_service
from app.domain import PlanKind, VerdictType
from app.mcp.cards import build_change_court_card, build_verdict_result_card

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUT_DIR = _REPO_ROOT / "m365" / "adaptive-cards" / "generated"

# Same trials and verdicts as the demo driver, so the exported cards match what runs.
_HEADLINE = [
    (
        "reschedule-conflict",
        "move the rehearsal to 2026-06-16",
        VerdictType.ACCEPT_ALTERNATIVE,
    ),
    ("reschedule", "move the rehearsal to 2026-06-17", VerdictType.APPROVE),
]

# Additional capabilities the same engine handles — exported with --all, not the recorded headline.
_ADDITIONAL = [
    ("meeting-actions", "create action items from standup", VerdictType.APPROVE),
    ("weekly-report", "post the Project X weekly report", VerdictType.APPROVE),
    (
        "customer-promise",
        "promise Customer A that SSO is GA by 2026-06-17",
        VerdictType.ACCEPT_ALTERNATIVE,
    ),
    (
        "vendor-access",
        "give the vendor access to Project X until the campaign is done",
        VerdictType.ACCEPT_ALTERNATIVE,
    ),
]


def _stabilize(card: dict[str, object]) -> dict[str, object]:
    """Replace the runtime thread_id in verdict buttons with a placeholder (stable re-exports)."""
    actions = card.get("actions")
    if isinstance(actions, list):
        for action in actions:
            data = action.get("data") if isinstance(action, dict) else None
            if isinstance(data, dict) and "thread_id" in data:
                data["thread_id"] = "<thread-id>"
    return card


def _write(path: Path, card: dict[str, object]) -> None:
    path.write_text(
        json.dumps(_stabilize(card), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  wrote {path.relative_to(_REPO_ROOT)}")


def run(*, include_additional: bool = False) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    service = build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )
    trials = _HEADLINE + _ADDITIONAL if include_additional else _HEADLINE
    for slug, request, verdict_type in trials:
        summary = service.submit_change(request)
        trial = service.get_trial(summary.thread_id)
        assert trial is not None
        _write(
            _OUT_DIR / f"{slug}-court.json",
            build_change_court_card(summary.thread_id, trial, status=summary.status),
        )

        if summary.status == "awaiting_verdict":
            selected = (
                PlanKind.SAFE_ALTERNATIVE
                if summary.plan_kind == PlanKind.SAFE_ALTERNATIVE.value
                else PlanKind.FEASIBLE
            )
            cast = service.cast_verdict(summary.thread_id, verdict_type, selected_plan=selected)
            status = cast.execution_status
        else:
            status = summary.status  # low risk: already executed on submission
        trial = service.get_trial(summary.thread_id)
        assert trial is not None
        # A placeholder audit id keeps the exported file reproducible (the real id is per-run).
        _write(
            _OUT_DIR / f"{slug}-result.json",
            build_verdict_result_card(trial, status=status, audit_id="<audit-id>"),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export Change Court Adaptive Card JSON (headline by default)."
    )
    parser.add_argument(
        "--all",
        dest="include_additional",
        action="store_true",
        help="also export cards for the additional capabilities the engine handles",
    )
    run(include_additional=parser.parse_args().include_additional)
