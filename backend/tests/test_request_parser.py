"""The deterministic parser routes natural-language variants into the right trial."""

from __future__ import annotations

import pytest

from app.adapters.parsers.deterministic import DeterministicRequestParser

_PARSER = DeterministicRequestParser()


@pytest.mark.parametrize(
    "raw",
    [
        "slip the launch from 2026-06-10 to 2026-06-17",  # canonical
        "move the launch milestone to 2026-06-17",
        "reschedule the launch from 2026-06-10 to 2026-06-17",
        "postpone the release to 2026-06-17",
    ],
)
def test_launch_variants(raw: str) -> None:
    change = _PARSER.parse(raw, change_id="c1")
    assert change.subject == "launch"
    assert change.due_by == "2026-06-17"
    assert change.requested_actions[0].capability_name == "github.update_milestone_due"


@pytest.mark.parametrize(
    "raw",
    [
        "promise Customer A that SSO is GA by 2026-06-17",  # canonical
        "tell Customer A that SSO will be available by 2026-06-17",
        "commit to the client that SSO is GA by 2026-06-17",
        "assure the customer SSO is ready by 2026-06-17",
    ],
)
def test_customer_promise_variants(raw: str) -> None:
    change = _PARSER.parse(raw, change_id="c1")
    assert change.subject == "sso-ga"
    assert change.due_by == "2026-06-17"


@pytest.mark.parametrize(
    "raw",
    [
        "give the vendor access to Project X until the campaign is done",  # canonical
        "let the agency into the Project X folder for now",
        "grant the contractor access to Project X",
        "share the Project X folder with an external supplier",
    ],
)
def test_vendor_access_variants(raw: str) -> None:
    change = _PARSER.parse(raw, change_id="c1")
    assert change.subject == "project-access"
    action = change.requested_actions[0]
    assert action.capability_name == "sharepoint.grant_folder_permission"
    assert "expiry" not in action.params  # options must add the expiry


def test_unrecognized_request_has_no_subject() -> None:
    change = _PARSER.parse("what's the weather like?", change_id="c1")
    assert change.subject is None
    assert change.requested_actions == []
