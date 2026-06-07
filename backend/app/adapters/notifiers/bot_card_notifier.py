"""Bot-chat card notifier: delivers the actionable approval card into the recipient's chat.

Where the activity-feed notifier raises a toast, this notifier puts the Change Court card itself —
with its Approve/Reject buttons — into the approver's personal bot conversation, so the toast's
deep link lands on something the approver can act on without typing. It composes presentation only:
trial data comes from injected readers, the card from the existing builders, and delivery is handed
to a queue (the sync/async seam) — no business logic, no I/O of its own.

Recipients without a stored conversation reference are still submitted — as create-jobs that ask
the sender to open the personal conversation (valid whenever the app is installed for the user).
Deployments where the bot cannot address users (no credentials) drop those jobs at the sender; the
activity-feed toast remains the floor.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.domain import ChangeStatus, TrialRecord
from app.mcp.cards import build_change_court_card, build_verdict_result_card
from app.ports.conversation_store import ConversationStore
from app.ports.notifier import ApprovalNotifier

logger = logging.getLogger(__name__)

Card = dict[str, object]
TrialReader = Callable[[str], TrialRecord | None]
NoteReader = Callable[[str], str]
StatusReader = Callable[[str], str | None]
SubmitJob = Callable[[dict[str, object] | None, Card, str, str], None]
RequestCardBuilder = Callable[..., Card]
ResultCardBuilder = Callable[..., Card]


class BotCardNotifier(ApprovalNotifier):
    """Builds the phase-appropriate card and enqueues it for proactive delivery."""

    def __init__(
        self,
        *,
        conversation_store: ConversationStore,
        submit_job: SubmitJob,
        trial_reader: TrialReader,
        note_reader: NoteReader,
        status_reader: StatusReader,
        request_card: RequestCardBuilder = build_change_court_card,
        result_card: ResultCardBuilder = build_verdict_result_card,
    ) -> None:
        self._store = conversation_store
        self._submit_job = submit_job
        self._trial_reader = trial_reader
        self._note_reader = note_reader
        self._status_reader = status_reader
        self._request_card = request_card
        self._result_card = result_card

    def approval_requested(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
        note: str,
    ) -> None:
        trial = self._trial_reader(thread_id)
        if trial is None:
            return
        card = self._request_card(
            thread_id,
            trial,
            status=ChangeStatus.AWAITING_APPROVAL.value,
            requester_note=note or self._note_reader(thread_id),
        )
        for upn in approver_upns:
            reference = self._store.get(upn)
            if reference is None:
                # No stored conversation reference — hand the sender a create-job instead. The
                # identity must be the Entra oid (what the directory keys on) for the channel to
                # resolve the member; logged so the fallback path is visible, not inferred.
                logger.info(
                    "proactive.create",
                    extra={"thread_id": thread_id, "event": "approval_requested", "identity": upn},
                )
            self._submit_job(reference, card, thread_id, upn)

    def decided(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approved: bool,
        decider_upn: str,
        note: str,
    ) -> None:
        reference = self._store.get(requester_upn)
        if reference is None:
            logger.info(
                "proactive.create",
                extra={"thread_id": thread_id, "event": "decided", "identity": requester_upn},
            )
        trial = self._trial_reader(thread_id)
        if trial is None:
            return
        status = self._status_reader(thread_id) or ("approved" if approved else "rejected")
        card = self._result_card(trial, status=status, audit_id=None, thread_id=thread_id)
        self._submit_job(reference, card, thread_id, requester_upn)

    def acknowledged(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
    ) -> None:
        # The ack reaches deciders through the activity-feed channel; the deciders' bot chat
        # already shows the result card, so there is no new card to deliver here.
        return
