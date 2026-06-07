"""Deterministic request parser: synonym keywords + natural-date extraction.

The always-on fallback that keeps the trials reproducible: it classifies a request into one of the
three trial subjects and extracts the requested action(s) (the intake guard validates them),
broadened beyond the canonical sentences so common rephrasings still route to the right trial.

Dates are read in any of three shapes — ISO (``2026-06-17``), month-name (``June 17``, ``17 June``),
and numeric (``6/17``, ``6/17/2026``) — taking the *last* one in reading order (so "from … to …"
resolves to the target). Year-less dates are anchored to the injected ``today``'s year. Purely
relative dates ("one week later", "seven days") are left to the LLM-backed parser, which resolves
them against ``today``; here they yield no date rather than a guess.
"""

from __future__ import annotations

import re
from datetime import date

from app.domain import Change, RequestedAction
from app.ports.request_parser import RequestParser

_LAUNCH_NOUNS = ("launch", "milestone", "release", "go-live", "ship")
_MOVE_VERBS = ("slip", "move", "push", "delay", "reschedule", "postpone", "shift", "bring")
_PROMISE_VERBS = ("promise", "tell", "commit", "assure", "guarantee", "pledge")
_PROMISE_OBJECTS = ("customer", "client", "sso", "ga", "available", "ready")
_VENDOR_WORDS = ("vendor", "contractor", "agency", "supplier", "guest", "external")
_MEETING_WORDS = (
    "action item",
    "action items",
    "follow-up",
    "follow-ups",
    "follow up",
    "meeting notes",
    "standup",
    "stand-up",
)
_REPORT_WORDS = ("weekly report", "status report", "weekly summary", "weekly update")

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH_NAMES = "|".join(_MONTHS)

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NUM_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
# "June 17", "June 17, 2026", "Sept. 3"
_MONTH_DAY = re.compile(rf"\b({_MONTH_NAMES})\.?\s+(\d{{1,2}})(?:,?\s+(\d{{4}}))?\b", re.IGNORECASE)
# "17 June", "3 Sept 2026"
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_NAMES})\.?(?:,?\s+(\d{{4}}))?\b", re.IGNORECASE)


def _has(text: str, *words: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def _safe_date(year: int | None, month: int, day: int) -> date | None:
    if year is None:
        return None
    try:
        return date(year, month, day)
    except ValueError:  # e.g. month 13 or day 32 — not a real date
        return None


def _norm_year(raw_year: str) -> int:
    year = int(raw_year)
    return year + 2000 if year < 100 else year


def _extract_date(raw: str, today: str | None) -> str | None:
    """Return the last date in the text as ISO, anchoring year-less dates to ``today``'s year."""
    anchor_year: int | None = None
    if today:
        try:
            anchor_year = date.fromisoformat(today).year
        except ValueError:
            anchor_year = None

    found: list[tuple[int, date]] = []

    def add(start: int, parsed: date | None) -> None:
        if parsed is not None:
            found.append((start, parsed))

    for m in _ISO_DATE.finditer(raw):
        add(m.start(), _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in _MONTH_DAY.finditer(raw):
        year = _norm_year(m.group(3)) if m.group(3) else anchor_year
        add(m.start(), _safe_date(year, _MONTHS[m.group(1).lower()], int(m.group(2))))
    for m in _DAY_MONTH.finditer(raw):
        year = _norm_year(m.group(3)) if m.group(3) else anchor_year
        add(m.start(), _safe_date(year, _MONTHS[m.group(2).lower()], int(m.group(1))))
    for m in _NUM_DATE.finditer(raw):
        year = _norm_year(m.group(3)) if m.group(3) else anchor_year
        add(m.start(), _safe_date(year, int(m.group(1)), int(m.group(2))))

    if not found:
        return None
    found.sort(key=lambda item: item[0])
    return found[-1][1].isoformat()


class DeterministicRequestParser(RequestParser):
    """Classifies the request by keywords and extracts natural dates (ISO / month / numeric)."""

    def __init__(self, *, today: str | None = None) -> None:
        # ``today`` anchors the year of year-less dates ("June 17"); injected by the container.
        self._today = today

    def parse(self, raw: str, *, change_id: str) -> Change:
        text = raw.lower()
        due_by = _extract_date(raw, self._today)
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
        elif _has(text, *_MEETING_WORDS):
            # Spoken follow-ups to track; the planner derives the tasks from the discussion.
            subject = "meeting-actions"
        elif _has(text, *_REPORT_WORDS):
            # An aggregation, not a requested capability; the planner composes the post.
            subject = "weekly-report"
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
