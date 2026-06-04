"""Build the Change Court Adaptive Card payloads from court data.

A pure presentation mapper: it turns a ``TrialRecord`` into an Adaptive Card dict per the contract
in docs/mcp-and-card-contract.md. No business logic — it reads data the service already produced.
Actions are phase-aware: the requester-review phase posts to ``send_for_approval`` /
``withdraw_change``, the approval phase to ``decide``, and the legacy verdict phase posts
``{thread_id, verdict_type, selected_plan}`` to the ``cast_verdict`` tool.
"""

from __future__ import annotations

from app.domain import ChangeStatus, EvidenceItem, PlanKind, TrialRecord, VerdictType

_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"


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


def _submit(title: str, data: dict[str, object]) -> dict[str, object]:
    return {"type": "Action.Submit", "title": title, "data": data}


def _requester_review_actions(thread_id: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Self-review phase: send on with a mandatory note, or give the change up."""
    note = _note_input("Why should this be approved? (required to send)", required=True)
    actions = [
        _submit("Send for approval", {"tool": "send_for_approval", "thread_id": thread_id}),
        _submit("Give up", {"tool": "withdraw_change", "thread_id": thread_id}),
    ]
    return actions, note


def _approval_actions(thread_id: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Approver phase: approve, or reject with a note (enforced by the service)."""
    note = _note_input("Reason (required when rejecting)", required=False)
    actions = [
        _submit("Approve", {"tool": "decide", "thread_id": thread_id, "approve": True}),
        _submit("Reject", {"tool": "decide", "thread_id": thread_id, "approve": False}),
    ]
    return actions, note


def build_change_court_card(
    thread_id: str, trial: TrialRecord, *, status: str = "", requester_note: str = ""
) -> dict[str, object]:
    """Render the Change Court card: change, impact, plan, approvers, and phase-aware actions."""
    change = trial.change
    body: list[dict[str, object]] = [
        _text("AI Change Court", weight="Bolder"),
        _text(change.raw_request),
    ]

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
                    _submit(
                        option.label or option.type.value,
                        {
                            "tool": "cast_verdict",
                            "thread_id": thread_id,
                            "verdict_type": option.type.value,
                            "selected_plan": selected_plan,
                        },
                    )
                )

    return {
        "type": "AdaptiveCard",
        "$schema": _SCHEMA,
        "version": "1.5",
        "body": body,
        "actions": actions,
    }


def build_verdict_result_card(
    trial: TrialRecord, *, status: str, audit_id: str | None
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
    return {
        "type": "AdaptiveCard",
        "$schema": _SCHEMA,
        "version": "1.5",
        "body": body,
    }
