"""Change Court playground bot — a thin Bot Framework surface over the court engine.

The bot reuses the backend in-process: it imports ``app.*`` from the sibling ``backend/`` project.
That package is an application (not pip-installable), so we put it on ``sys.path`` here, before any
submodule imports ``app.container`` / ``app.mcp.cards``. The bot owns no business logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

# repo-root/m365/playground-bot/courtbot/__init__.py -> repo-root/backend
_BACKEND = Path(__file__).resolve().parents[3] / "backend"
if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
