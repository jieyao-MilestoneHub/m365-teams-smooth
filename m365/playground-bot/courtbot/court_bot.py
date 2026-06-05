"""Re-export of the backend's CourtBot.

The bot handler lives in the backend (``app.bot.court_bot``) so the production ``/api/messages``
endpoint and this local Playground host share one implementation over one court engine. This module
keeps the Playground's import path stable; ``courtbot/__init__`` already puts the backend package on
``sys.path``.
"""

from __future__ import annotations

from app.bot.court_bot import WELCOME, CourtBot, _principal, _text_card

__all__ = ["WELCOME", "CourtBot", "_principal", "_text_card"]
