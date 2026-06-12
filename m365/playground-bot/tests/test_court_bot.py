"""CourtBot mapping tests.

The first tests drive the *real* engine fully mocked (offline, deterministic — the same path as
scripts/demo.py and the Playground demo) through the two identity gates: the requester submits and
sends, an authorized approver decides, and the run resumes to the result card. The rest pin
routing with fakes that mirror the same contract minimally.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from app.config import Settings
from app.container import build_court_service
from app.domain.principal import Principal
from app.services.court_service import CourtService

from courtbot.court_bot import WELCOME, CourtBot, _principal

USER_A = Principal(oid="user-a", upn="user-a", display_name="User A")
USER_B = Principal(oid="user-b", upn="user-b", display_name="User B")

# A directory granting User B every approver role, so B can decide any quorum A's requests raise.
_ALL_ROLES_FOR_B = ",".join(
    f"{role}:user-b" for role in ("eng_lead", "comms", "account_owner", "security_lead", "manager")
)


class _Account:
    """The slice of a Bot Framework ChannelAccount the bot reads."""

    def __init__(self, account_id: str, name: str, aad_object_id: str | None = None) -> None:
        self.id = account_id
        self.name = name
        self.aad_object_id = aad_object_id


def _texts(card: dict[str, Any]) -> list[str]:
    return [b.get("text", "") for b in card.get("body", []) if b.get("type") == "TextBlock"]


def _actions(card: dict[str, Any]) -> list[dict[str, Any]]:
    actions = card.get("actions", [])
    assert isinstance(actions, list)
    return actions


@pytest.fixture
def service(tmp_path: Path) -> CourtService:
    db_url = f"sqlite:///{tmp_path.as_posix()}/bot.db"
    return build_court_service(
        Settings(
            force_all_mock=True,
            db_url=db_url,
            dry_run_default=True,
            approver_directory=_ALL_ROLES_FOR_B,
        )
    )


def test_request_then_two_gate_round_trip(service: CourtService) -> None:
    bot = CourtBot(service)

    # The refusal card holds at the requester self-review gate: send / give up.
    card = bot.respond(
        text="promise Customer A that SSO is GA by 2026-06-17", value=None, actor=USER_A
    )
    assert card["type"] == "AdaptiveCard"
    assert any("REJECTED" in t for t in _texts(card))
    assert [a["data"]["tool"] for a in _actions(card)] == ["send_for_approval", "withdraw_change"]
    thread_id = _actions(card)[0]["data"]["thread_id"]

    sent = bot.respond(
        text=None,
        value={"tool": "send_for_approval", "thread_id": thread_id, "note": "safer plan attached"},
        actor=USER_A,
    )
    assert [a["data"]["tool"] for a in _actions(sent)] == ["decide", "decide"]

    result = bot.respond(
        text=None, value={"tool": "decide", "thread_id": thread_id, "approve": True}, actor=USER_B
    )
    assert any("Verdict recorded" in t for t in _texts(result))
    assert service.get_status(thread_id) == "done"


def test_repeat_decide_is_idempotent(service: CourtService) -> None:
    bot = CourtBot(service)
    card = bot.respond(
        text="promise Customer A that SSO is GA by 2026-06-17", value=None, actor=USER_A
    )
    thread_id = _actions(card)[0]["data"]["thread_id"]
    bot.respond(
        text=None,
        value={"tool": "send_for_approval", "thread_id": thread_id, "note": "ready"},
        actor=USER_A,
    )
    decide = {"tool": "decide", "thread_id": thread_id, "approve": True}
    first = bot.respond(text=None, value=decide, actor=USER_B)
    second = bot.respond(text=None, value=decide, actor=USER_B)
    assert _texts(first) == _texts(second)
    assert service.get_status(thread_id) == "done"


class _Summary:
    def __init__(self, status: str) -> None:
        self.thread_id = "thread-1"
        self.status = status


class _FakeService:
    """Records calls so routing can be asserted without the real engine.

    Mirrors the identity-bound contract minimally: submit requires a requester, and the two
    gates (send/withdraw, then decide) are the only mutating calls the bot can route.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def submit_change(
        self, raw: str, *, source: str, run_mode: Any = None, requester: Any = None
    ) -> _Summary:
        self.calls.append(("submit", raw, source, run_mode, requester))
        return _Summary("awaiting_requester_review")

    def get_trial(self, thread_id: str) -> dict[str, str]:
        return {"trial_for": thread_id}

    def get_status(self, thread_id: str) -> str:
        return "awaiting_approval"

    def requester_note(self, thread_id: str) -> str:
        return ""

    def send_for_approval(self, thread_id: str, *, actor: Any, note: str) -> _Summary:
        self.calls.append(("send", thread_id, actor, note))
        return _Summary("awaiting_approval")

    def withdraw_change(self, thread_id: str, *, actor: Any) -> _Summary:
        self.calls.append(("withdraw", thread_id, actor))
        return _Summary("withdrawn")

    def decide(self, thread_id: str, *, actor: Any, approve: bool, note: str = "") -> _Summary:
        self.calls.append(("decide", thread_id, actor, approve, note))
        return _Summary("done")


def _bot_with_fake() -> tuple[CourtBot, _FakeService]:
    fake = _FakeService()
    bot = CourtBot(
        fake,
        request_card=lambda tid, trial, **kw: {"type": "AdaptiveCard", "_req": [tid, trial]},
        result_card=lambda trial, *, status, audit_id, **kw: {
            "type": "AdaptiveCard",
            "_res": [status, audit_id],
        },
    )
    return bot, fake


def test_blank_input_returns_welcome() -> None:
    bot, _ = _bot_with_fake()
    card = bot.respond(text="   ", value=None)
    assert _texts(card) == [WELCOME]


def test_text_without_actor_renders_guidance() -> None:
    bot, fake = _bot_with_fake()
    card = bot.respond(text="slip the launch", value=None)
    assert any("needs a sender" in t for t in _texts(card))
    assert fake.calls == []


def test_text_opens_trial_and_renders_request_card() -> None:
    bot, fake = _bot_with_fake()
    card = bot.respond(text="slip the launch", value=None, actor=USER_A)
    assert card["_req"] == ["thread-1", {"trial_for": "thread-1"}]
    # run_mode is None: the bot defers to the deployment's DRY_RUN_DEFAULT (see #279).
    assert fake.calls[0] == ("submit", "slip the launch", "playground", None, USER_A)


def test_send_value_routes_to_the_send_gate() -> None:
    bot, fake = _bot_with_fake()
    card = bot.respond(
        text=None,
        value={"tool": "send_for_approval", "thread_id": "thread-1", "note": "ready"},
        actor=USER_A,
    )
    # Still awaiting approval: the bot re-renders the trial card in its new phase.
    assert card["_req"] == ["thread-1", {"trial_for": "thread-1"}]
    assert fake.calls[0] == ("send", "thread-1", USER_A, "ready")


def test_decide_value_routes_to_the_decide_gate_and_renders_result() -> None:
    bot, fake = _bot_with_fake()
    card = bot.respond(
        text=None,
        value={"tool": "decide", "thread_id": "thread-1", "approve": True},
        actor=USER_B,
    )
    assert card["_res"] == ["done", None]
    assert fake.calls[0] == ("decide", "thread-1", USER_B, True, "")


def test_legacy_verdict_value_falls_through_to_welcome() -> None:
    # The identity-free verdict route is gone: a value naming no recognized tool is not an
    # action, so the turn renders the welcome guidance and touches no service gate.
    bot, fake = _bot_with_fake()
    card = bot.respond(
        text=None,
        value={"thread_id": "t", "verdict_type": "accept_alternative"},
    )
    assert _texts(card) == [WELCOME]
    assert fake.calls == []


class _FakeActivity:
    """The slice of a Bot Framework activity that on_message_activity touches."""

    def __init__(self, activity_id: str | None, text: str | None, value: Any = None) -> None:
        self.id = activity_id
        self.text = text
        self.value = value
        self.from_property = _Account("user-x", "Xavier")


class _FakeTurnContext:
    def __init__(self, activity: _FakeActivity) -> None:
        self.activity = activity
        self.sent: list[Any] = []

    async def send_activity(self, activity: Any) -> None:
        self.sent.append(activity)


async def test_redelivered_activity_sends_card_once() -> None:
    """The channel may redeliver the same activity; only the first delivery posts a card."""
    bot, fake = _bot_with_fake()
    decide = {"tool": "decide", "thread_id": "thread-1", "approve": True}
    contexts = [_FakeTurnContext(_FakeActivity("act-1", None, decide)) for _ in range(4)]
    for ctx in contexts:
        await bot.on_message_activity(ctx)
    assert sum(len(ctx.sent) for ctx in contexts) == 1
    assert len([c for c in fake.calls if c[0] == "decide"]) == 1


async def test_distinct_activities_each_send_a_card() -> None:
    bot, _ = _bot_with_fake()
    first = _FakeTurnContext(_FakeActivity("act-1", "slip the launch"))
    second = _FakeTurnContext(_FakeActivity("act-2", "slip the launch"))
    await bot.on_message_activity(first)
    await bot.on_message_activity(second)
    assert len(first.sent) == 1
    assert len(second.sent) == 1


async def test_activity_without_id_is_never_deduplicated() -> None:
    bot, _ = _bot_with_fake()
    contexts = [_FakeTurnContext(_FakeActivity(None, "slip the launch")) for _ in range(2)]
    for ctx in contexts:
        await bot.on_message_activity(ctx)
    assert sum(len(ctx.sent) for ctx in contexts) == 2


# --- identity-aware approval flow against the real (mocked) engine -------------------------------


@pytest.fixture
def approval_service(tmp_path: Path) -> CourtService:
    """A real engine whose directory authorizes B (eng lead) and C (comms): launch-slip quorum."""
    db_url = f"sqlite:///{tmp_path.as_posix()}/approval.db"
    return build_court_service(
        Settings(
            force_all_mock=True,
            db_url=db_url,
            dry_run_default=True,
            approver_directory="eng_lead:user-b,comms:user-c",
        )
    )


def test_two_user_approval_round_trip(approval_service: CourtService) -> None:
    bot = CourtBot(approval_service)

    # User A submits: the trial holds at the requester self-review gate.
    card = bot.respond(
        text="slip the launch from 2026-06-10 to 2026-06-17", value=None, actor=USER_A
    )
    tools = [a["data"]["tool"] for a in _actions(card)]
    assert tools == ["send_for_approval", "withdraw_change"]
    thread_id = _actions(card)[0]["data"]["thread_id"]

    # User A sends it on with the mandatory note.
    card = bot.respond(
        text=None,
        value={"tool": "send_for_approval", "thread_id": thread_id, "note": "ready"},
        actor=USER_A,
    )
    assert [a["data"]["tool"] for a in _actions(card)] == ["decide", "decide"]
    assert any("Requester's note: ready" in t for t in _texts(card))

    # User B pulls the queue and approves; the reschedule quorum is "any" (need = 1), so a single
    # sign-off from a distinct approver completes it and the run resumes to a result card.
    queue = bot.respond(text="queue", value=None, actor=USER_B)
    assert any(thread_id in str(a.get("data", {}).get("thread_id")) for a in _actions(queue))
    result = bot.respond(
        text=None,
        value={"tool": "decide", "thread_id": thread_id, "approve": True},
        actor=USER_B,
    )
    # The result card is a TL;DR: a success headline + one-line outcome, not a status/step log.
    assert any("Verdict recorded" in t for t in _texts(result))
    assert not any("hit a failure" in t for t in _texts(result))


def test_self_approval_renders_refusal(approval_service: CourtService) -> None:
    bot = CourtBot(approval_service)
    card = bot.respond(
        text="slip the launch from 2026-06-10 to 2026-06-17", value=None, actor=USER_A
    )
    thread_id = _actions(card)[0]["data"]["thread_id"]
    bot.respond(
        text=None,
        value={"tool": "send_for_approval", "thread_id": thread_id, "note": "ready"},
        actor=USER_A,
    )
    refusal = bot.respond(
        text=None,
        value={"tool": "decide", "thread_id": thread_id, "approve": True},
        actor=USER_A,
    )
    assert any("⛔" in t for t in _texts(refusal))
    assert approval_service.get_status(thread_id) == "awaiting_approval"


def test_reject_without_note_renders_guidance(approval_service: CourtService) -> None:
    bot = CourtBot(approval_service)
    card = bot.respond(
        text="slip the launch from 2026-06-10 to 2026-06-17", value=None, actor=USER_A
    )
    thread_id = _actions(card)[0]["data"]["thread_id"]
    bot.respond(
        text=None,
        value={"tool": "send_for_approval", "thread_id": thread_id, "note": "ready"},
        actor=USER_A,
    )
    guidance = bot.respond(
        text=None,
        value={"tool": "decide", "thread_id": thread_id, "approve": False, "note": "  "},
        actor=USER_B,
    )
    assert any("note is required" in t for t in _texts(guidance))


def test_queue_empty_for_unauthorized_user(approval_service: CourtService) -> None:
    bot = CourtBot(approval_service)
    card = bot.respond(text="queue", value=None, actor=USER_A)
    assert any("No trials" in t for t in _texts(card))


def test_principal_mapping_prefers_aad_object_id() -> None:
    teams = _principal(_Account("29:abc", "Alice", aad_object_id="oid-1"))
    assert teams is not None and teams.oid == "oid-1"
    playground = _principal(_Account("user-x", "Xavier"))
    assert playground is not None and playground.oid == "user-x"
    other = _principal(_Account("user-y", "Yara"))
    assert other is not None and not playground.same_as(other)
