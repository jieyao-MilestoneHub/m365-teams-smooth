"""The subject→grounding-phrase map stays aligned with the registered gatherers."""

from __future__ import annotations

from app.agent.gatherers import GATHERERS
from app.agent.grounding_queries import GROUNDING_QUERIES, grounding_query


def test_every_gatherer_subject_has_a_grounding_phrase() -> None:
    # One source of truth: a subject with a gatherer must have a grounding phrase, and vice versa.
    assert set(GROUNDING_QUERIES) == set(GATHERERS)


def test_grounding_query_returns_the_subject_phrase() -> None:
    assert grounding_query("launch", "raw request") == GROUNDING_QUERIES["launch"]


def test_grounding_query_falls_back_to_the_raw_request() -> None:
    assert grounding_query(None, "raw request") == "raw request"
    assert grounding_query("unregistered-subject", "raw request") == "raw request"
