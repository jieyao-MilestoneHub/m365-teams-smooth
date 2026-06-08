"""Build the Change Court Adaptive Card payloads from court data.

A pure presentation mapper: it turns a ``TrialRecord`` into an Adaptive Card dict per the contract
in docs/reference/mcp-and-card-contract.md. No business logic — it renders what the service made.
Actions are phase-aware ``Action.Execute`` buttons (universal actions, so a bot can refresh the
card in place): the requester-review phase routes to ``send_for_approval`` / ``withdraw_change``,
the approval phase to ``decide``, and the legacy verdict phase carries
``{thread_id, verdict_type, selected_plan}`` for the ``cast_verdict`` tool. Each action's ``data``
keeps the ``tool`` key so ``Action.Submit``-style value routing resolves identically.
"""

from __future__ import annotations

from collections.abc import Callable

from app.domain import ChangeStatus, EvidenceItem, PlanKind, TrialRecord, VerdictType

_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"

# Builds the signed run-page URL for a thread (None disables the link). Injected by the
# composition root — the card stays a pure mapper with no settings or crypto of its own.
RunLink = Callable[[str], str | None]

_PIPELINE_STAGES = (
    "intake", "impact", "options", "policy", "verdict", "execute", "verify", "audit"
)

_GLYPH_DONE, _GLYPH_WAIT, _GLYPH_IDLE, _GLYPH_RUN, _GLYPH_FAIL = "✓", "⏸", "○", "⏳", "⛔"

# The verdict gate sits between policy and execute (index 4 of the strip).
_GATE_WAITING = {
    ChangeStatus.AWAITING_REQUESTER_REVIEW.value,
    ChangeStatus.AWAITING_VERDICT.value,
    ChangeStatus.AWAITING_APPROVAL.value,
}


def _stage_glyphs(status: str) -> list[str] | None:
    """Per-stage glyphs for a lifecycle status, or ``None`` when no strip applies."""
    if status == ChangeStatus.BLOCKED.value:
        return [_GLYPH_FAIL] + [_GLYPH_IDLE] * 7  # hallucination guard refused at intake
    if status in (ChangeStatus.INTAKE.value, ChangeStatus.EVALUATING.value):
        return [_GLYPH_DONE, _GLYPH_RUN] + [_GLYPH_IDLE] * 6
    if status in _GATE_WAITING:
        return [_GLYPH_DONE] * 4 + [_GLYPH_WAIT] + [_GLYPH_IDLE] * 3
    if status == ChangeStatus.EXECUTING.value:
        return [_GLYPH_DONE] * 5 + [_GLYPH_RUN, _GLYPH_IDLE, _GLYPH_IDLE]
    if status == ChangeStatus.DONE.value:
        return [_GLYPH_DONE] * 8
    if status == ChangeStatus.FAILED.value:
        # verify and audit still run after a failing step (containment, not a crash).
        return [_GLYPH_DONE] * 5 + [_GLYPH_FAIL, _GLYPH_DONE, _GLYPH_DONE]
    if status in (ChangeStatus.REJECTED.value, ChangeStatus.WITHDRAWN.value):
        return [_GLYPH_DONE] * 4 + [_GLYPH_FAIL] + [_GLYPH_IDLE] * 3
    return None


def _stage_strip(status: str) -> dict[str, object] | None:
    """One compact TextBlock tracing the pipeline (the run page is the live, detailed view)."""
    glyphs = _stage_glyphs(status)
    if glyphs is None:
        return None
    text = " → ".join(f"{g} {name}" for g, name in zip(glyphs, _PIPELINE_STAGES, strict=True))
    block = _text(text)
    block["isSubtle"] = True
    block["spacing"] = "Small"
    return block


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


def _evidence_rows(items: list[EvidenceItem], *, emphasize: bool) -> list[dict[str, object]]:
    """Render evidence items as card rows, with their grounded citations indented underneath."""
    rows: list[dict[str, object]] = []
    for item in items:
        weight = "Bolder" if emphasize else None
        rows.append(_text(f"• [{item.system}] {item.summary}", weight=weight))
        for fact in item.grounded:
            rows.append(_text(f"    ↳ {fact.claim} ({fact.citation})"))
    return rows


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
    strip = _stage_strip(status)
    if strip is not None:
        body.append(strip)

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
        decisive = [i for i in impact.items if i.severity == "high"]
        others = [i for i in impact.items if i.severity != "high"]
        if decisive:
            body.append(_text("⚠ Decisive evidence", weight="Bolder", color="Attention"))
            body.extend(_evidence_rows(decisive, emphasize=True))
        if others:
            body.append(_text("Impact evidence", weight="Bolder"))
            body.extend(_evidence_rows(others, emphasize=False))

    options = trial.options
    if options is not None:
        is_alt = options.kind is PlanKind.SAFE_ALTERNATIVE
        label = "Safe alternative" if is_alt else "Proposed plan"
        body.append(_text(f"{label}: {options.rationale}", weight="Bolder"))
        for step in options.steps:
            body.append(_text(f"• {step.capability.name}"))

    quorum = trial.quorum
    if quorum is not None and quorum.required_approvers:
        roles = ", ".join(a.role.value for a in quorum.required_approvers)
        body.append(_text(f"Approvers required ({quorum.policy}): {roles}"))

    if requester_note:
        body.append(_text(f"Requester's note: {requester_note}"))

    # Phase-aware actions: the identity-aware statuses get their gate's buttons; every other
    # status keeps the legacy verdict buttons so the identity-free flow renders unchanged.
    actions: list[dict[str, object]]
    if status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value:
        actions, note_input = _requester_review_actions(thread_id)
        body.append(note_input)
    elif status == ChangeStatus.AWAITING_APPROVAL.value:
        actions, note_input = _approval_actions(thread_id)
        body.append(note_input)
    else:
        selected_plan = options.kind.value if options is not None else "feasible"
        actions = []
        if quorum is not None:
            for option in quorum.verdict_options:
                actions.append(
                    _execute(
                        option.label or option.type.value,
                        "cast_verdict",
                        {
                            "thread_id": thread_id,
                            "verdict_type": option.type.value,
                            "selected_plan": selected_plan,
                        },
                    )
                )

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
    """Render the post-verdict card: outcome plus per-step results and any rollback hints."""
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
    else:
        body = [_text("Verdict recorded", weight="Bolder")]
    strip = _stage_strip(status)
    if strip is not None:
        body.append(strip)
    body.append(_text(f"Status: {status}"))
    if audit_id:
        body.append(_text(f"Audit: {audit_id}"))
    for result in trial.results:
        line = f"• {result.step_id}: {result.status.value}"
        if result.status.value == "dry_run":
            line += " (predicted)"
        body.append(_text(line))
        if result.rollback is not None:
            body.append(_text(f"    ↩ rollback: {result.rollback.instruction}"))
    for verification in trial.verifications:
        if not verification.matched:
            issues = "; ".join(verification.mismatches)
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
