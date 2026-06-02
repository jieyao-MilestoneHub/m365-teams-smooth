"""Application configuration, loaded from environment variables (.env-driven).

The documented surface lives in the repository-root ``.env.example``. Nothing here
holds a secret default; credentials are supplied per environment via env vars.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the backend process."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Persistence ---
    db_url: str = "sqlite:///./data/app.db"

    # --- Agent behavior ---
    dry_run_default: bool = True

    # --- Integrations ---
    # Per-system selection of real vs mock adapters, comma-separated "system:mode".
    integration_mode: str = "github:real"
    # Force every integration into mock mode (runs with zero external credentials).
    force_all_mock: bool = False
    # Required only when the GitHub adapter runs in real mode.
    github_token: str = ""
    # Target repository for the real GitHub adapter, as "owner/name" (a throwaway test repo).
    github_repo: str = ""

    # --- LLM provider (empty -> offline fake provider) ---
    llm_api_key: str = ""
    llm_model: str = ""

    # --- Knowledge / Foundry IQ (empty endpoint -> offline fake provider) ---
    # Keyless auth via DefaultAzureCredential (az login / managed identity); no key here.
    knowledge_search_endpoint: str = ""
    knowledge_base_name: str = ""
    knowledge_source_name: str = ""

    # --- MCP OAuth2 resource server (empty -> local dev issuer) ---
    oauth_issuer: str = ""
    oauth_audience: str = ""
    oauth_jwks_url: str = ""

    def integration_modes(self) -> dict[str, str]:
        """Parse ``integration_mode`` into a ``{system: mode}`` map.

        ``"github:real,outlook:mock"`` becomes ``{"github": "real", "outlook": "mock"}``.
        When :attr:`force_all_mock` is set, every listed system resolves to ``"mock"``.
        Systems omitted here fall back to mock in the registry (see the adapter registry).
        """
        modes: dict[str, str] = {}
        for raw_pair in self.integration_mode.split(","):
            pair = raw_pair.strip()
            if not pair:
                continue
            system, _, mode = pair.partition(":")
            system = system.strip().lower()
            mode = mode.strip().lower() or "mock"
            if system:
                modes[system] = "mock" if self.force_all_mock else mode
        return modes
