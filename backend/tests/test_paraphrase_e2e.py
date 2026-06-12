"""Natural rephrasings drive the whole court (not just the parser) into the right trial.

The strongest rebuttal to "it only handles fixed demo phrasing": feed non-canonical sentences
through the fully-wired ``CourtService`` and assert each routes to the correct trial with the right
safety outcome. The parser is pinned to a fixed ``today`` so the run is deterministic.
"""

from __future__ import annotations

import pytest

from app.adapters.parsers.deterministic import DeterministicRequestParser
from app.config import Settings
from app.container import build_court_service
from app.domain import ChangeStatus, PlanKind
from app.services.court_service import CourtService
from tests.conftest import REQUESTER


def _service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True),
        request_parser=DeterministicRequestParser(today="2026-06-01"),
    )


_SAFE = PlanKind.SAFE_ALTERNATIVE.value
_FEASIBLE = PlanKind.FEASIBLE.value


@pytest.mark.parametrize(
    ("raw", "unsafe", "plan_kind"),
    [
        ("Promise Customer A production SSO by June 17.", True, _SAFE),
        ("Let the agency into Project X until the campaign wraps.", True, _SAFE),
        ("Push Q3 launch from June 10 to June 17.", False, _FEASIBLE),
    ],
)
def test_natural_phrasing_drives_the_right_trial(raw: str, unsafe: bool, plan_kind: str) -> None:
    summary = _service().submit_change(raw, requester=REQUESTER)
    assert summary.status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value
    assert summary.unsafe is unsafe
    assert summary.plan_kind == plan_kind
