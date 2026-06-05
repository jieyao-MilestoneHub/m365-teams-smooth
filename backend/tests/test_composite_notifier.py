"""The composite notifier fans out to every channel and isolates per-channel failures."""

from __future__ import annotations

from app.adapters.notifiers import CompositeNotifier, FakeNotifier
from app.ports.notifier import ApprovalNotifier


class _ExplodingNotifier(ApprovalNotifier):
    def approval_requested(self, **_: object) -> None:
        raise RuntimeError("channel down")

    def decided(self, **_: object) -> None:
        raise RuntimeError("channel down")

    def acknowledged(self, **_: object) -> None:
        raise RuntimeError("channel down")


def test_fans_out_to_every_channel() -> None:
    first, second = FakeNotifier(), FakeNotifier()
    composite = CompositeNotifier([first, second])

    composite.approval_requested(
        thread_id="t1", title="t", requester_upn="r@x", approver_upns=["a@x"], note="n"
    )
    composite.decided(
        thread_id="t1", title="t", requester_upn="r@x", approved=True, decider_upn="a@x", note=""
    )

    for fake in (first, second):
        assert len(fake.requested) == 1
        assert len(fake.decisions) == 1


def test_one_channel_failure_never_suppresses_the_other() -> None:
    surviving = FakeNotifier()
    composite = CompositeNotifier([_ExplodingNotifier(), surviving])

    composite.approval_requested(
        thread_id="t1", title="t", requester_upn="r@x", approver_upns=["a@x"], note="n"
    )
    composite.decided(
        thread_id="t1", title="t", requester_upn="r@x", approved=False, decider_upn="a@x", note="x"
    )

    assert len(surviving.requested) == 1
    assert len(surviving.decisions) == 1
