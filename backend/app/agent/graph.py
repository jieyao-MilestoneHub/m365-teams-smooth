"""Court graph wiring: the linear pipeline compiled with the durable verdict interrupt.

This module and the runner are the only places that call into LangGraph, isolating the engine's API
(and any version churn) from the rest of the app. The graph is compiled with
``interrupt_before=["execute"]`` so every run suspends at the verdict gate and is resumed from its
checkpoint by ``thread_id``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.instrument import instrument
from app.agent.state import CourtState

Node = Callable[[CourtState], CourtState]


def build_court_graph(
    *,
    intake: Node,
    impact: Node,
    options: Node,
    policy: Node,
    execute: Node,
    audit: Node,
    checkpointer: object,
) -> Any:
    """Wire intake → impact → options → policy → [interrupt] → execute → audit and compile it."""
    # Typed Any to keep the engine's API (and version churn) confined to this module + the runner.
    graph: Any = StateGraph(CourtState)
    # The wrapper binds correlation IDs and logs start/end + duration; nodes stay transparent.
    graph.add_node("intake", instrument(intake, "intake"))
    graph.add_node("impact", instrument(impact, "impact"))
    graph.add_node("options", instrument(options, "options"))
    graph.add_node("policy", instrument(policy, "policy"))
    graph.add_node("execute", instrument(execute, "execute"))
    graph.add_node("audit", instrument(audit, "audit"))

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "impact")
    graph.add_edge("impact", "options")
    graph.add_edge("options", "policy")
    graph.add_edge("policy", "execute")
    graph.add_edge("execute", "audit")
    graph.add_edge("audit", END)

    return graph.compile(checkpointer=checkpointer, interrupt_before=["execute"])
