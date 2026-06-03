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

    # --- Microsoft Graph (read-only real evidence: Outlook calendar, SharePoint folders) ---
    # App-only (client-credentials) auth; needs admin-consented Calendars.Read + Sites.Read.All.
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    # The user whose calendar holds the security-review event (Customer Promise evidence).
    outlook_calendar_upn: str = ""
    # The SharePoint site whose default library holds the ProjectX folders (Vendor Access evidence).
    sharepoint_site_id: str = ""

    # --- LLM provider (empty -> offline fake provider + deterministic parser) ---
    llm_api_key: str = ""
    llm_model: str = ""
    # Azure OpenAI for agentic request parsing. Endpoint + deployment enable the LLM-backed parser;
    # auth is keyless (DefaultAzureCredential) unless llm_api_key is set.
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # --- Knowledge / Foundry IQ (empty endpoint -> offline fake provider) ---
    # Keyless auth via DefaultAzureCredential (az login / managed identity); no key here.
    knowledge_search_endpoint: str = ""
    knowledge_base_name: str = ""
    knowledge_source_name: str = ""

    # --- MCP OAuth2 resource server (empty -> local dev issuer) ---
    oauth_issuer: str = ""
    oauth_audience: str = ""
    oauth_jwks_url: str = ""

    # --- Deployment ---
    # Public HTTPS origin this backend is reachable at (e.g. https://change-court.example.com).
    # The MCP resource-server URL is derived as "{public_base_url}/mcp"; empty -> localhost default.
    public_base_url: str = ""

    def mcp_resource_url(self) -> str:
        """The MCP endpoint's externally reachable URL (``{public_base_url}/mcp``).

        Falls back to the local dev origin when :attr:`public_base_url` is unset, so the resource
        server advertises a correct address once deployed behind a public HTTPS host.
        """
        origin = self.public_base_url.rstrip("/") or "http://localhost:8000"
        return f"{origin}/mcp"

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
