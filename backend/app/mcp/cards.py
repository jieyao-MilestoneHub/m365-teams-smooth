"""Build the Change Court Adaptive Card payloads from court data.

A pure presentation mapper: it turns a ``TrialRecord`` into an Adaptive Card dict.
No business logic — it renders what the service made.
Actions are phase-aware ``Action.Execute`` buttons (universal actions, so a bot can refresh the
card in place): the requester-review phase routes to ``send_for_approval`` / ``withdraw_change``,
and the approval phase to ``decide``; every other phase renders read-only. Each action's ``data``
keeps the ``tool`` key so ``Action.Submit``-style value routing resolves identically.
"""

from __future__ import annotations

from collections.abc import Callable

from app.domain import (
    ChangeStatus,
    ImpactEvidence,
    PlanKind,
    StepResult,
    StepStatus,
    TrialRecord,
    VerdictType,
)

_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"

# Builds the signed run-page URL for a thread (None disables the link). Injected by the
# composition root — the card stays a pure mapper with no settings or crypto of its own.
RunLink = Callable[[str], str | None]

# The card is a TL;DR: the decision and its decisive reason. The full pipeline trace, every
# evidence item, the grounded policy texts, and per-step before/after + rollback hints all live on
# the read-only run page — so these evidence kinds (the prosecutor's executed reads and prose
# assessment, and the bulk grounded-policy block) are summarised here, not enumerated.
_OMITTED_EVIDENCE_KINDS = frozenset({"agentic", "assessment", "grounding"})
_MAX_CARD_EVIDENCE = 4
_MAX_RATIONALE_CHARS = 180


def _deliberation_row(trial: TrialRecord) -> list[dict[str, object]]:
    """A one-line reasoning teaser — the Prosecutor's read, else the Defender's; full trace on the
    run page. Kept subtle so the card stays a decision TL;DR."""
    delib = trial.deliberation
    if delib is None or not delib.entries:
        return []
    by_node = {e.node: e for e in delib.entries}
    entry = by_node.get("impact") or by_node.get("options")
    if entry is None or not entry.rationale:
        return []
    who = entry.role.capitalize() if entry.role else "Court"
    row = _text(f"🧠 {who}: {_clip(entry.rationale, _MAX_RATIONALE_CHARS)}")
    row["isSubtle"] = True
    row["spacing"] = "Small"
    return [row]


def _run_link_row(run_link: RunLink | None, thread_id: str) -> list[dict[str, object]]:
    """The run-page deep link as a single subtle body row — empty when no link is available.

    One link, one place: a markdown link in the body rather than a parallel ``Action.OpenUrl``
    button. It renders in every host (including webviews that suppress OpenUrl actions) and keeps
    the card's action row dedicated to decisions, so each surface carries a single focus.
    """
    if run_link is None or not thread_id:
        return []
    url = run_link(thread_id)
    if not url:
        return []
    row = _text(f"[View pipeline run]({url})")
    row["isSubtle"] = True
    row["spacing"] = "Small"
    return [row]


def _text(
    text: str, *, weight: str | None = None, wrap: bool = True, color: str | None = None
) -> dict[str, object]:
    block: dict[str, object] = {"type": "TextBlock", "text": text, "wrap": wrap}
    if weight:
        block["weight"] = weight
    if color:
        block["color"] = color
    return block


def _clip(text: str, limit: int) -> str:
    """Trim to a single readable line; the full text is on the run page."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _subtle(block: dict[str, object]) -> dict[str, object]:
    block["isSubtle"] = True
    block["spacing"] = "Small"
    return block


def _impact_rows(impact: ImpactEvidence) -> list[dict[str, object]]:
    """A curated, TL;DR impact view: the decisive evidence (with its citation, not the full policy
    text) and a few touched systems. The prosecutor's reads/assessment and the bulk grounded
    policies collapse to one 'grounded in N facts' pointer — all of it stays on the run page."""
    rows: list[dict[str, object]] = []
    visible = [i for i in impact.items if i.kind not in _OMITTED_EVIDENCE_KINDS]
    decisive = [i for i in visible if i.severity == "high"][:_MAX_CARD_EVIDENCE]
    others = [i for i in visible if i.severity != "high"]

    if decisive:
        rows.append(_text("⚠ Decisive evidence", weight="Bolder", color="Attention"))
        for item in decisive:
            rows.append(_text(f"• [{item.system}] {item.summary}", weight="Bolder"))
            citations = list(dict.fromkeys(f.citation for f in item.grounded if f.citation))
            if citations:
                rows.append(_subtle(_text("    ↳ " + "; ".join(citations))))

    shown_others = others[: max(_MAX_CARD_EVIDENCE - len(decisive), 0)]
    if shown_others:
        rows.append(_text("Impact evidence", weight="Bolder"))
        for item in shown_others:
            rows.append(_text(f"• [{item.system}] {item.summary}"))

    hidden = len(visible) - len(decisive) - len(shown_others)
    grounded = sum(len(i.grounded) for i in impact.items)
    tail = []
    if hidden > 0:
        tail.append(f"+{hidden} more impact item(s)")
    if grounded:
        tail.append(f"grounded in {grounded} governance fact(s)")
    if tail:
        rows.append(_subtle(_text(" · ".join(tail) + " — see the run page")))
    return rows


def _outcome_line(results: list[StepResult]) -> str:
    """One line of what execution did — plan-agnostic, from step statuses (detail on the page)."""
    if not results:
        return ""
    total = len(results)
    applied = sum(1 for r in results if r.status is StepStatus.OK)
    failed = sum(1 for r in results if r.status is StepStatus.FAILED)
    predicted = sum(1 for r in results if r.status is StepStatus.DRY_RUN)
    line = (
        f"{total} step(s) predicted (dry-run)"
        if predicted == total
        else f"{applied}/{total} step(s) applied"
    )
    if 0 < predicted < total:
        line += f" ({predicted} predicted)"
    return f"{line}, {failed} failed" if failed else line


def _resource_label(url: str) -> str:
    """A human label for a modified-resource link, inferred from the URL shape."""
    if "/milestone" in url:
        return "View the updated milestone"
    if "#issuecomment" in url:
        return "View the comment"
    if "/issues/" in url or "/pull/" in url:
        return "View the issue"
    return "View the updated resource"


def _note_input(placeholder: str, *, required: bool) -> dict[str, object]:
    """The note input the requester/approver fills in alongside the card's actions."""
    field: dict[str, object] = {
        "type": "Input.Text",
        "id": "note",
        "isMultiline": True,
        "placeholder": placeholder,
    }
    if required:
        field["isRequired"] = True
        field["errorMessage"] = "A note is required."
    return field


def _execute(title: str, verb: str, data: dict[str, object]) -> dict[str, object]:
    """An ``Action.Execute`` button: ``verb`` routes the bot's invoke handler, and ``data`` keeps
    the ``tool`` key so legacy ``Action.Submit``-style value routing resolves identically."""
    return {"type": "Action.Execute", "title": title, "verb": verb, "data": {"tool": verb, **data}}


def _requester_review_actions(thread_id: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Self-review phase: send on with a mandatory note, or give the change up."""
    note = _note_input("Why should this be approved? (required to send)", required=True)
    actions = [
        _execute("Send for approval", "send_for_approval", {"thread_id": thread_id}),
        _execute("Give up", "withdraw_change", {"thread_id": thread_id}),
    ]
    return actions, note


def _approval_actions(thread_id: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Approver phase: approve, or reject with a note (enforced by the service)."""
    note = _note_input("Reason (required when rejecting)", required=False)
    actions = [
        _execute("Approve", "decide", {"thread_id": thread_id, "approve": True}),
        _execute("Reject", "decide", {"thread_id": thread_id, "approve": False}),
    ]
    return actions, note


def build_change_court_card(
    thread_id: str,
    trial: TrialRecord,
    *,
    status: str = "",
    requester_note: str = "",
    run_link: RunLink | None = None,
) -> dict[str, object]:
    """Render the Change Court card: change, impact, plan, approvers, and phase-aware actions."""
    change = trial.change
    body: list[dict[str, object]] = [
        _text("AI Change Court", weight="Bolder"),
        _text(change.raw_request),
    ]

    if status == ChangeStatus.BLOCKED.value:
        # Hallucination guard: an unsupported action was refused at intake. Say so plainly — this
        # is the one signal the dropped stage strip used to carry.
        body.append(
            _text("⛔ Blocked — the request includes an unsupported action",
                  weight="Bolder", color="Attention")
        )

    risk = trial.risk
    if risk is not None:
        color = {"high": "Attention", "medium": "Warning", "low": "Good"}.get(risk.level.value)
        body.append(_text(f"Risk: {risk.level.value.upper()}", weight="Bolder", color=color))
    if change.unsafe:
        body.append(
            _text(
                "⛔ REJECTED as requested — proposing a safer alternative",
                weight="Bolder",
                color="Attention",
            )
        )
        if change.unsafe_reason:
            body.append(_text(change.unsafe_reason, color="Attention"))

    impact = trial.impact
    if impact is not None and impact.items:
        body.extend(_impact_rows(impact))

    options = trial.options
    if options is not None:
        is_alt = options.kind is PlanKind.SAFE_ALTERNATIVE
        label = "Safe alternative" if is_alt else "Proposed plan"
        rationale = _clip(options.rationale, _MAX_RATIONALE_CHARS)
        body.append(_text(f"{label}: {rationale}", weight="Bolder"))
        for step in options.steps:
            body.append(_text(f"• {step.capability.name}"))

    quorum = trial.quorum
    if quorum is not None and quorum.required_approvers:
        roles = ", ".join(a.role.value for a in quorum.required_approvers)
        body.append(_text(f"Approvers required ({quorum.policy}): {roles}"))
    elif quorum is not None:
        # The exception-based gate's routine path, stated where the requester sees it: this
        # change adds no approval layer — their own confirmation is what executes it.
        body.append(
            _text(
                "Approval required: none — the requester's confirmation executes it.",
                weight="Bolder",
                color="Good",
            )
        )

    if requester_note:
        body.append(_text(f"Requester's note: {requester_note}"))

    # Phase-aware actions: only the two identity gates are actionable — the requester's
    # self-review and the authorized approver's decision. Every other phase renders read-only.
    actions: list[dict[str, object]] = []
    if status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value:
        actions, note_input = _requester_review_actions(thread_id)
        body.append(note_input)
    elif status == ChangeStatus.AWAITING_APPROVAL.value:
        actions, note_input = _approval_actions(thread_id)
        body.append(note_input)

    body.extend(_deliberation_row(trial))
    body.extend(_run_link_row(run_link, thread_id))

    return {
        "type": "AdaptiveCard",
        "$schema": _SCHEMA,
        "version": "1.5",
        "body": body,
        "actions": actions,
    }


def build_verdict_result_card(
    trial: TrialRecord,
    *,
    status: str,
    audit_id: str | None,
    thread_id: str = "",
    run_link: RunLink | None = None,
) -> dict[str, object]:
    """Render the post-verdict card as a TL;DR: the outcome in one line plus the audit id. The
    per-step before/after, predicted effects, and rollback hints live on the run page and the
    append-only audit — only failures and verification problems surface here."""
    verdict = trial.verdict
    refused_for_safe_alt = (
        trial.change.unsafe
        and verdict is not None
        and verdict.type is VerdictType.ACCEPT_ALTERNATIVE
    )
    if refused_for_safe_alt:
        body: list[dict[str, object]] = [
            _text("✅ Safe alternative executed", weight="Bolder", color="Good"),
            _text("Refused the request as posed; ran the safer plan instead."),
        ]
    elif status == ChangeStatus.FAILED.value:
        body = [_text("⚠ Verdict recorded — execution hit a failure", weight="Bolder",
                      color="Attention")]
    else:
        body = [_text("✅ Verdict recorded", weight="Bolder", color="Good")]

    outcome = _outcome_line(trial.results)
    if outcome:
        body.append(_text(outcome))
    if audit_id:
        body.append(_subtle(_text(f"Audit: {audit_id}")))

    # A direct link to each resource the run actually modified, so a reviewer can open it.
    for result in trial.results:
        if result.status is StepStatus.OK and result.resource_url:
            body.append(_text(f"[{_resource_label(result.resource_url)} ↗]({result.resource_url})"))

    # Surface only what needs attention; successful steps need no per-step recap here.
    for result in trial.results:
        if result.status is StepStatus.FAILED:
            line = f"⚠ {result.step_id} failed"
            if result.error:
                line += f": {_clip(result.error, 120)}"
            body.append(_text(line, weight="Bolder", color="Attention"))
    for verification in trial.verifications:
        if not verification.matched:
            issues = _clip("; ".join(verification.mismatches), 120)
            body.append(
                _text(
                    f"⚠ {verification.step_id} verification: {issues}",
                    weight="Bolder",
                    color="Warning",
                )
            )
    body.extend(_run_link_row(run_link, thread_id))
    return {
        "type": "AdaptiveCard",
        "$schema": _SCHEMA,
        "version": "1.5",
        "body": body,
    }
