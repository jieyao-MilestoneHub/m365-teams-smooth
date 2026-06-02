"""Put the bot project root and the sibling backend on the path so tests import both."""

from __future__ import annotations

import sys
from pathlib import Path

_BOT_ROOT = Path(__file__).resolve().parents[1]  # m365/playground-bot (for `import courtbot`)
_BACKEND = Path(__file__).resolve().parents[3] / "backend"  # repo-root/backend (for `import app`)
for _p in (_BOT_ROOT, _BACKEND):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
