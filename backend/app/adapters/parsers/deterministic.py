"""Deterministic request parser: synonym keywords + ISO-date extraction.

The always-on fallback that keeps the trials reproducible: it classifies a request into one of the
three trial subjects and extracts the requested action(s) (the intake guard validates them),
broadened beyond the canonical sentences so common rephrasings still route to the right trial.
"""

from __future__ import annotations

import re

from app.domain import Change, RequestedAction
from app.ports.request_parser import RequestParser

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

_LAUNCH_NOUNS = ("launch", "milestone", "release", "go-live", "ship")
_MOVE_VERBS = ("slip", "move", "push", "delay", "reschedule", "postpone", "shift", "bring")
_PROMISE_VERBS = ("promise", "tell", "commit", "assure", "guarantee", "pledge")
_PROMISE_OBJECTS = ("customer", "client", "sso", "ga", "available", "ready")
_VENDOR_WORDS = ("vendor", "contractor", "agency", "supplier", "guest", "external")


def _has(text: str, *words: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


class DeterministicRequestParser(RequestParser):
    """Classifies the request by keywords and extracts explicit ISO dates."""

    def parse(self, raw: str, *, change_id: str) -> Change:
        text = raw.lower()
        dates = _ISO_DATE.findall(raw)
        due_by = dates[-1] if dates else None
        actions: list[RequestedAction] = []
        subject: str | None = None

        is_vendor = _has(text, *_VENDOR_WORDS) or (
            "access" in text and ("project" in text or "folder" in text or "share" in text)
        )
        if is_vendor:
            subject = "project-access"
            actions.append(
                RequestedAction(
                    system="sharepoint",
                    capability_name="sharepoint.grant_folder_permission",
                    verb="grant",
                    # Deliberately broad and undated — options narrows this to least-privilege.
                    params={
                        "path": "/ProjectX",
                        "principal": "vendor@example.com",
                        "role": "write",
                    },
                )
            )
        elif (_has(text, *_PROMISE_VERBS) and _has(text, *_PROMISE_OBJECTS)) or (
            "generally available" in text
        ):
            # A commitment, not a single capability; options produces the safe alternative.
            subject = "sso-ga"
        elif _has(text, *_LAUNCH_NOUNS) and _has(text, *_MOVE_VERBS):
            subject = "launch"
            actions.append(
                RequestedAction(
                    system="github",
                    capability_name="github.update_milestone_due",
                    verb="update",
                    params={"milestone": "Launch", "due_on": due_by},
                )
            )
            if _has(text, "delete") and _has(text, "repo", "repository"):
                actions.append(
                    RequestedAction(
                        system="github",
                        capability_name="github.delete_repo",  # unregistered — the guard rejects it
                        verb="delete",
                        params={"repo": "launch"},
                    )
                )

        return Change(
            change_id=change_id,
            raw_request=raw,
            subject=subject,
            due_by=due_by,
            requested_actions=actions,
        )
