"""Bot host configuration. Host/port only — no business config (the engine reads its own env)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    """Where the bot listens for the Agents Playground / Bot Framework Emulator."""

    model_config = SettingsConfigDict(env_prefix="BOT_")

    host: str = "localhost"
    port: int = 3978

    # File-backed SQLite so a run survives the submit -> verdict gap across turns. The checkpoint
    # connection and the audit/ledger engine must share one file, so ``:memory:`` is unsafe here.
    db_url: str = "sqlite:///./data/playground-bot.db"
