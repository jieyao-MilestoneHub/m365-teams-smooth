"""The bot-chat card notifier enqueues actionable cards only for reachable recipients."""

from __future__ import annotations

from typing import Any

from app.adapters.notifiers.bot_card_notifier import BotCardNotifier
from app.config import Settings
from app.container import build_court_service
from app.domain import RunMode
from app.domain.principal import Principal
from app.services.court_service import CourtService
from tests.conftest import InMemoryConversationStore

_DIRECTORY = (
    "eng_lead:approver@example.com,comms:approver@example.com,"
    "security_lead:approver@example.com,account_owner:approver@example.com,"
    "manager:approver@example.com"
)
_REQUESTER = Principal(oid="oid-req", upn="requester@example.com", display_name="req")
_REFERENCE: dict[str, object] = {
    "conversation": {"id": "conv-approver"},
    "service_url": "https://example.test",
}


def _service() -> CourtService:
    return build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            approver_directory=_DIRECTORY,
        )
    )


def _notifier(
    service: CourtService, store: InMemoryConversationStore, jobs: list[tuple[Any, ...]]
) -> BotCardNotifier:
    return BotCardNotifier(
        conversation_store=store,
        submit_job=lambda ref, card, thread_id, recipient: jobs.append(
            (ref, card, thread_id, recipient)
        ),
        trial_reader=service.get_trial,
        note_reader=service.requester_note,
        status_reader=service.get_status,
    )


def _awaiting_approval_thread(service: CourtService) -> str:
    summary = service.submit_change(
        "slip the launch from 2026-06-10 to 2026-06-17",
        source="test",
        run_mode=RunMode.DRY_RUN,
        requester=_REQUESTER,
    )
    return summary.thread_id


def test_approval_requested_enqueues_decide_card_per_reachable_approver() -> None:
    service = _service()
    store = InMemoryConversationStore()
    store.save(oid="oid-app", upn="approver@example.com", reference=_REFERENCE)
    jobs: list[tuple[Any, ...]] = []
    thread_id = _awaiting_approval_thread(service)

    _notifier(service, store, jobs).approval_requested(
        thread_id=thread_id,
        title="slip the launch",
        requester_upn="requester@example.com",
        approver_upns=["approver@example.com", "offline@example.com"],
        note="please review",
    )

    # A continue-job for the installed approver; a create-job for the one without a reference.
    assert len(jobs) == 2
    reference, card, job_thread, recipient = jobs[0]
    assert reference == _REFERENCE and job_thread == thread_id
    assert recipient == "approver@example.com"
    verbs = [a["verb"] for a in card["actions"]]
    assert verbs == ["decide", "decide"]  # the actionable approval card, not a toast
    assert "please review" in str(card)
    offline_reference, _, _, offline_recipient = jobs[1]
    assert offline_reference is None and offline_recipient == "offline@example.com"


def test_decided_enqueues_result_card_for_requester() -> None:
    service = _service()
    store = InMemoryConversationStore()
    store.save(oid="oid-req", upn="requester@example.com", reference=_REFERENCE)
    jobs: list[tuple[Any, ...]] = []
    thread_id = _awaiting_approval_thread(service)
    service.send_for_approval(thread_id, actor=_REQUESTER, note="please review")
    approver = Principal(oid="oid-app", upn="approver@example.com", display_name="app")
    service.decide(thread_id, actor=approver, approve=True)

    _notifier(service, store, jobs).decided(
        thread_id=thread_id,
        title="slip the launch",
        requester_upn="requester@example.com",
        approved=True,
        decider_upn="approver@example.com",
        note="",
    )

    assert len(jobs) == 1
    _, card, _, _ = jobs[0]
    assert "actions" not in card  # terminal result card — nothing further to click


def test_approval_card_delivered_when_directory_and_store_key_on_oid() -> None:
    # The realistic shape: the bot captured the approver's reference under their Entra oid (it has
    # no UPN), and the directory is keyed on the same oid. Lookup by oid must hit and deliver.
    directory = ",".join(
        f"{role}:oid-app"
        for role in ("eng_lead", "comms", "security_lead", "account_owner", "manager")
    )
    service = build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            approver_directory=directory,
        )
    )
    store = InMemoryConversationStore()
    store.save(oid="oid-app", upn="", reference=_REFERENCE)  # bot stores by oid, no UPN
    jobs: list[tuple[Any, ...]] = []
    thread_id = _awaiting_approval_thread(service)

    _notifier(service, store, jobs).approval_requested(
        thread_id=thread_id,
        title="slip the launch",
        requester_upn="req",
        approver_upns=["oid-app"],  # the directory hands the oid through
        note="please review",
    )
    assert len(jobs) == 1


def test_unreachable_recipients_enqueue_create_jobs() -> None:
    # No stored reference -> the job carries no reference but names the recipient, asking the
    # sender to create the conversation (the bot-credentialed deployments can; others drop it).
    service = _service()
    jobs: list[tuple[Any, ...]] = []
    thread_id = _awaiting_approval_thread(service)
    notifier = _notifier(service, InMemoryConversationStore(), jobs)

    notifier.approval_requested(
        thread_id=thread_id,
        title="t",
        requester_upn="requester@example.com",
        approver_upns=["approver@example.com"],
        note="n",
    )
    notifier.decided(
        thread_id=thread_id,
        title="t",
        requester_upn="requester@example.com",
        approved=False,
        decider_upn="approver@example.com",
        note="no",
    )

    assert [(ref, recipient) for ref, _, _, recipient in jobs] == [
        (None, "approver@example.com"),
        (None, "requester@example.com"),
    ]
