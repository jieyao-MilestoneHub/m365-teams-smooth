"""Parameter sanitizers for the real integration adapters — the trust boundary.

Step/query params reach a real external API here, and their values originate from the request
parser or the LLM-backed planner, neither of which constrains a *value* (the capability guard only
checks that required keys are present). These helpers reject path-traversal and malformed
identifiers before they are interpolated into an API path, so a crafted request cannot reach a
resource other than the one the adapter is scoped to.
"""

from __future__ import annotations

import re

from app.domain.errors import IntegrationError

# GitHub owner / repo names: alphanumerics plus . _ - (no slashes, no traversal).
_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
# SharePoint path segments additionally allow spaces (folder display names).
_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9._ -]+$")


def safe_repo(value: str) -> str:
    """Return ``value`` if it is a well-formed ``owner/name`` repo, else raise IntegrationError."""
    parts = value.split("/")
    if len(parts) != 2 or not all(_SEGMENT.fullmatch(p) for p in parts):
        raise IntegrationError(f"invalid repository '{value}'")
    return value


def safe_path(value: str) -> str:
    """Return ``value`` if every segment is a safe name (no traversal), else raise.

    A leading slash is allowed; empty input maps to ``/``. Segments may contain spaces.
    """
    segments = [s for s in value.split("/") if s]
    # '.' and '..' match the segment charset but are traversal — reject them explicitly.
    if any(s in {".", ".."} or not _PATH_SEGMENT.fullmatch(s) for s in segments):
        raise IntegrationError(f"invalid path '{value}'")
    return "/" + "/".join(segments)
