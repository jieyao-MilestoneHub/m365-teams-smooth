"""Adapter parameter sanitizers reject traversal/malformed values at the trust boundary."""

from __future__ import annotations

import pytest

from app.adapters.integrations.validation import safe_path, safe_repo
from app.domain.errors import IntegrationError


@pytest.mark.parametrize("value", ["octocat/hello-world", "a.b_c/x-y.z", "Org123/Repo_1"])
def test_safe_repo_accepts_well_formed(value: str) -> None:
    assert safe_repo(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "../other/repo",  # traversal
        "owner/../repo",  # traversal mid-path
        "owner",  # missing name
        "owner/name/extra",  # too many segments
        "owner/na me",  # space (not allowed in repo names)
        "owner/na/me",
        "",  # empty
        "owner/",  # empty segment
        "ow ner/name",
    ],
)
def test_safe_repo_rejects_malformed(value: str) -> None:
    with pytest.raises(IntegrationError):
        safe_repo(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/ProjectX", "/ProjectX"),
        ("ProjectX", "/ProjectX"),
        ("/ProjectX/Customer Data", "/ProjectX/Customer Data"),
        ("/ProjectX/sub/folder", "/ProjectX/sub/folder"),
        ("", "/"),
    ],
)
def test_safe_path_normalizes_valid(value: str, expected: str) -> None:
    assert safe_path(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "/ProjectX/../Secret",  # traversal
        "..",
        "/a/b/../../etc",
        "/Project:X",  # ':' would break the Graph root:/<path>: addressing
        "/Project\tX",  # control char
    ],
)
def test_safe_path_rejects_traversal_and_control(value: str) -> None:
    with pytest.raises(IntegrationError):
        safe_path(value)
