"""Build the Change Court Adaptive Card payloads from court data.

A pure presentation mapper: it turns a ``TrialRecord`` into an Adaptive Card dict per the contract
in docs/mcp-and-card-contract.md. No business logic — it reads data the service already produced.
Verdict buttons post back ``{thread_id, verdict_type, selected_plan}`` to the ``cast_verdict`` tool.
"""

from __future__ import annotations

from app.domain import TrialRecord

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


def build_change_court_card(thread_id: str, trial: TrialRecord) -> dict[str, object]:
    """Render the Change Court card: change, impact, plan, approvers, and verdict actions."""
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
        note = "⚠ Unsafe as requested — a safer alternative is proposed."
        if change.unsafe_reason:
            note = f"{note} {change.unsafe_reason}"
        body.append(_text(note, color="Attention"))

    impact = trial.impact
    if impact is not None and impact.items:
        body.append(_text("Impact evidence", weight="Bolder"))
        for item in impact.items:
            body.append(_text(f"• [{item.system}] {item.summary}"))
            for fact in item.grounded:
                body.append(_text(f"    ↳ {fact.claim} ({fact.citation})"))

    options = trial.options
    if options is not None:
        label = "Safe alternative" if options.kind.value == "safe_alternative" else "Proposed plan"
        body.append(_text(f"{label}: {options.rationale}", weight="Bolder"))
        for step in options.steps:
            body.append(_text(f"• {step.capability.name}"))

    quorum = trial.quorum
    if quorum is not None and quorum.required_approvers:
        roles = ", ".join(a.role.value for a in quorum.required_approvers)
        body.append(_text(f"Approvers required ({quorum.policy}): {roles}"))

    selected_plan = options.kind.value if options is not None else "feasible"
    actions: list[dict[str, object]] = []
    if quorum is not None:
        for option in quorum.verdict_options:
            actions.append(
                {
                    "type": "Action.Submit",
                    "title": option.label or option.type.value,
                    "data": {
                        "tool": "cast_verdict",
                        "thread_id": thread_id,
                        "verdict_type": option.type.value,
                        "selected_plan": selected_plan,
                    },
                }
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
    body: list[dict[str, object]] = [
        _text("Verdict recorded", weight="Bolder"),
        _text(f"Status: {status}"),
    ]
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
