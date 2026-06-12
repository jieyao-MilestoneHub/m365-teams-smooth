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

    def analyzed(self, **_: object) -> None:
        raise RuntimeError("channel down")


class _BarePeopleChannel(ApprovalNotifier):
    """A channel implementing only the abstract people-facing events."""

    def approval_requested(self, **_: object) -> None:
        return

    def decided(self, **_: object) -> None:
        return

    def acknowledged(self, **_: object) -> None:
        return


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


def test_analyzed_fans_out_and_survives_a_failing_channel() -> None:
    surviving = FakeNotifier()
    composite = CompositeNotifier([_ExplodingNotifier(), surviving])

    composite.analyzed(thread_id="t1", title="t", requester_upn="r@x")

    assert surviving.analyzed_events == [
        {"thread_id": "t1", "title": "t", "requester_upn": "r@x"}
    ]


def test_a_bare_people_channel_inherits_a_silent_analyzed() -> None:
    # The port defaults analyzed to a no-op: a channel built for people-facing approval events
    # stays silent for analysis-only conclusions unless it opts in.
    channel = _BarePeopleChannel()
    channel.analyzed(thread_id="t1", title="t", requester_upn="r@x")  # must not raise
