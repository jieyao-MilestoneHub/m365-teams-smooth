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

    # --- Microsoft Graph (real evidence + contained writes: Outlook, SharePoint) ---
    # App-only (client-credentials) auth; needs admin-consented Calendars.ReadWrite + Mail.ReadWrite
    # (Outlook evidence + contained event/draft writes) and Sites.Read.All (SharePoint evidence).
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
    # Query planning depth before hybrid + semantic rerank: "minimal" | "low" | "medium".
    knowledge_reasoning_effort: str = "medium"
    # Offline grounding corpus (empty -> the bundled assets/knowledge-corpus). The offline provider
    # chunks and cites these markdown files, so credential-free runs ground real policy text.
    knowledge_corpus_dir: str = ""

    # --- Input shield / guardrail (empty endpoint -> offline heuristic) ---
    # Azure AI Content Safety endpoint for Prompt Shields; keyless via DefaultAzureCredential.
    content_safety_endpoint: str = ""
    # When a screened input is flagged as a prompt-injection attempt, skip the agentic LLM step and
    # fall back to the deterministic path. Set false to screen-and-log without blocking.
    guardrail_blocking: bool = True

    # --- MCP OAuth2 resource server (empty -> local dev issuer) ---
    oauth_issuer: str = ""
    oauth_audience: str = ""
    oauth_jwks_url: str = ""

    # --- Observability ---
    # Verbosity and output shape for the structured logger; "text" aids local-dev readability.
    log_level: str = "INFO"
    log_format: str = "json"  # "json" | "text"
    # Default per-request wall-clock budget for adapters that lack an explicit one.
    http_timeout_seconds: float = 10.0
    # Closes the OpenAI no-timeout gap on the LLM-backed parser.
    llm_timeout_seconds: float = 30.0
    # Output ceiling per LLM call (the parser needs a small JSON object, never long text).
    llm_max_tokens: int = 1024
    # Boundary cap on a submitted change request. A change request is a sentence or two in chat;
    # anything past this is rejected (422 / invalid_params), never silently truncated.
    max_request_chars: int = 1000
    # Cap on the additional reads the agentic evidence loop may execute per trial.
    max_agentic_reads: int = 5
    # Overall guard on a single graph run; on expiry the checkpoint is left resumable.
    graph_timeout_seconds: float = 60.0
    # Idempotency-aware retry policy for transient adapter failures (exponential backoff + jitter).
    retry_max_attempts: int = 3
    retry_backoff_base_seconds: float = 0.2
    retry_backoff_max_seconds: float = 2.0
    # Toggles collection/exposure of the in-process metrics registry.
    metrics_enabled: bool = True
    # Retention window for finished trials' working storage (checkpoints + verdict claims);
    # the audit log is permanent and never purged. See app/services/maintenance.py.
    retention_days: int = 30

    # --- Approvals (separation of duties) ---
    # Map approver roles to identities (UPN or oid), comma-separated "role:identity" (a role may
    # repeat). e.g. "security_lead:joel@x,account_owner:joel@x". Empty -> no authorized approvers,
    # so identity-aware enforcement stays off and the legacy single-verdict path is used.
    approver_directory: str = ""

    # --- Notifications (approval channel) ---
    # "off" (default) or "teams" — push approval events to Teams activity feeds via Microsoft
    # Graph (app-only TeamsActivity.Send; reuses the GRAPH_* credentials; the activity types are
    # declared in the Teams app manifest). Delivery is best-effort and never blocks the workflow.
    notify_mode: str = "off"
    # Click-through target of the notification toast (a Teams deep link, "…/l/…" — Graph rejects
    # a bare domain). Empty -> derived from the bot app id (the bot chat, where the proactive
    # approval card lands), falling back to the Teams home when no bot is configured.
    notify_link_url: str = ""
    # The catalog app id of the Teams app (disambiguates the installed app for notifications).
    notify_teams_app_id: str = ""
    # When INTEGRATION_MODE includes teams:real, downstream Teams writes (weekly-report post,
    # reschedule announcement) send a real Graph activity notification to this UPN. Reuses GRAPH_*
    # + the admin-consented TeamsActivity.Send; empty -> teams falls back to the in-memory mock.
    teams_notify_recipient: str = ""

    # --- Bot surface (POST /api/messages) ---
    # The Azure Bot's app registration. Empty bot_app_id -> anonymous Bot Framework auth, which is
    # what the local Playground/Emulator expects; set all of these when deployed behind Azure Bot
    # Service. The app is multi-tenant by default so the bot resource and the sign-in tenant may
    # live in different tenants.
    bot_app_id: str = ""
    bot_app_password: str = ""
    bot_app_type: str = "MultiTenant"
    bot_app_tenant_id: str = ""
    # Channel service URL used when the sender must CREATE a conversation (recipient never
    # contacted the bot). Teams' global entry routes to the tenant's region; override when a
    # captured reference shows a regional URL (e.g. .../apac/).
    bot_service_url: str = "https://smba.trafficmanager.net/teams/"

    # --- Deployment ---
    # Public HTTPS origin this backend is reachable at (e.g. https://change-court.example.com).
    # The MCP resource-server URL is derived as "{public_base_url}/mcp"; empty -> localhost default.
    public_base_url: str = ""

    # --- Run page (read-only pipeline inspection) ---
    # HMAC secret signing per-trial run-page deep links ("/runs/{thread_id}?t=..."). Empty ->
    # the run page is disabled entirely (requests 404); an unverifiable link advertises nothing.
    run_link_secret: str = ""

    def mcp_resource_url(self) -> str:
        """The MCP endpoint's externally reachable URL (``{public_base_url}/mcp``).

        Falls back to the local dev origin when :attr:`public_base_url` is unset, so the resource
        server advertises a correct address once deployed behind a public HTTPS host.
        """
        origin = self.public_base_url.rstrip("/") or "http://localhost:8000"
        return f"{origin}/mcp"

    def notification_link_url(self) -> str:
        """The toast's click-through deep link.

        An explicit ``notify_link_url`` wins; otherwise the bot chat (where the proactive approval
        card lands) when a bot is configured, then the installed app, then the Teams home.
        Graph requires a deep link ("…/l/…"), so the derived forms are preferred.
        """
        if self.notify_link_url:
            return self.notify_link_url
        if self.bot_app_id:
            return f"https://teams.microsoft.com/l/chat/0/0?users=28:{self.bot_app_id}"
        if self.notify_teams_app_id:
            return f"https://teams.microsoft.com/l/app/{self.notify_teams_app_id}"
        return "https://teams.microsoft.com"

    def approver_map(self) -> dict[str, set[str]]:
        """Parse ``approver_directory`` into ``{role: {identity_key, ...}}`` (all lowercased)."""
        mapping: dict[str, set[str]] = {}
        for raw_pair in self.approver_directory.split(","):
            role, _, identity = raw_pair.strip().partition(":")
            role, identity = role.strip().lower(), identity.strip().lower()
            if role and identity:
                mapping.setdefault(role, set()).add(identity)
        return mapping

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
