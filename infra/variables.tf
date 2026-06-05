variable "subscription_id" {
  type        = string
  description = "Azure subscription to deploy into."
}

variable "azure_tenant_id" {
  type        = string
  description = "Tenant id of the Azure subscription that hosts the runtime resources (azurerm)."
}

variable "entra_tenant_id" {
  type        = string
  description = "Entra ID (Microsoft 365) tenant id for the app registration and user sign-in. Forms the OAuth issuer/JWKS URLs. May differ from azure_tenant_id when the subscription and the M365 tenant are separate."
}

variable "location" {
  type        = string
  description = "Azure region for all resources."
  default     = "eastus"
}

variable "name" {
  type        = string
  description = "Base name for resources (also the Container App name / DNS label). Lowercase, alphanumeric/hyphen."
  default     = "changecourt"
}

variable "image_repository" {
  type        = string
  description = "Image repository name within the ACR (pushed by `docker push`)."
  default     = "change-court"
}

variable "image_tag" {
  type        = string
  description = "Image tag to run."
  default     = "latest"
}

variable "min_replicas" {
  type        = number
  description = "0 scales to zero when idle (cheapest; cold start on first call). Set 1 for a warm demo."
  default     = 0
}

variable "force_all_mock" {
  type        = bool
  description = "Run every integration as a mock (reliable demo, zero external credentials)."
  default     = true
}

variable "integration_mode" {
  type        = string
  description = "Per-system real/mock when force_all_mock is false, e.g. \"github:real\"."
  default     = "github:real"
}

variable "dry_run_default" {
  type        = bool
  description = "Whether new decisions default to dry-run. Set false to run approved plans live."
  default     = true
}

variable "github_token" {
  type        = string
  description = "Optional: token for the real GitHub adapter (only when github runs real). Stored as a Container App secret."
  default     = ""
  sensitive   = true
}

variable "github_repo" {
  type        = string
  description = "Optional: owner/name for the real GitHub adapter."
  default     = ""
}

# --- Microsoft Graph read-only evidence (Outlook calendar + SharePoint folders) ---
# App-only (client-credentials) auth. Supplied only when outlook/sharepoint run real; otherwise the
# backend's graph-ready gate stays false and those systems fall back to mock in the cloud.
variable "graph_tenant_id" {
  type        = string
  description = "Optional: Entra tenant id for the app-only Graph client (real Outlook/SharePoint reads)."
  default     = ""
}

variable "graph_client_id" {
  type        = string
  description = "Optional: app (client) id for the app-only Graph client."
  default     = ""
}

variable "graph_client_secret" {
  type        = string
  description = "Optional: client secret for the app-only Graph client. Stored as a Container App secret."
  default     = ""
  sensitive   = true
}

variable "outlook_calendar_upn" {
  type        = string
  description = "Optional: UPN whose calendar holds the security-review event (Customer Promise evidence)."
  default     = ""
}

variable "sharepoint_site_id" {
  type        = string
  description = "Optional: SharePoint site id whose library holds the ProjectX folders (Vendor Access evidence)."
  default     = ""
}

variable "app_display_name" {
  type        = string
  description = "Display name for the Entra ID app registration."
  default     = "AI Change Court"
}

# --- Knowledge grounding (Azure AI Search agentic retrieval) ---
# All optional: leave empty and the backend's knowledge provider stays on the offline fallback.
# The Container App authenticates keylessly via its managed identity, so the search and OpenAI
# resources must grant it data-plane roles — pass their resource ids to create the assignments.
variable "knowledge_search_endpoint" {
  type        = string
  description = "Optional: Azure AI Search endpoint URL for knowledge grounding."
  default     = ""
}

variable "knowledge_base_name" {
  type        = string
  description = "Optional: knowledge base (agent) name on the search service."
  default     = ""
}

variable "knowledge_source_name" {
  type        = string
  description = "Optional: knowledge source name backing the knowledge base."
  default     = ""
}

variable "knowledge_search_resource_id" {
  type        = string
  description = "Optional: resource id of the Azure AI Search service; grants the app's identity Search Index Data Reader."
  default     = ""
}

variable "knowledge_openai_resource_id" {
  type        = string
  description = "Optional: resource id of the Azure OpenAI account the knowledge base answers with; grants the app's identity Cognitive Services OpenAI User."
  default     = ""
}

# --- Agentic roles (Azure OpenAI) ---
# Set endpoint + deployment AND force_all_mock = false to make the Prosecutor/Defender agentic;
# otherwise the roles stay deterministic. llm_api_key is optional (omit for keyless via the app's
# managed identity, which then needs the Cognitive Services OpenAI User role on the account).
variable "azure_openai_endpoint" {
  type        = string
  description = "Optional: Azure OpenAI endpoint, e.g. https://<name>.openai.azure.com."
  default     = ""
}

variable "azure_openai_deployment" {
  type        = string
  description = "Optional: Azure OpenAI chat deployment name (GPT-4o-class; must accept max_tokens)."
  default     = ""
}

variable "llm_api_key" {
  type        = string
  description = "Optional: Azure OpenAI API key. Stored as a Container App secret. Omit for keyless."
  default     = ""
  sensitive   = true
}

# --- Separation of duties ---
variable "approver_directory" {
  type        = string
  description = "Optional: role->identity map, comma-separated 'role:upn' pairs. Empty = legacy flow."
  default     = ""
}

# --- Entra app registration (cross-tenant) ---
# Same-tenant: leave create_entra_app = true and Terraform registers the app. Cross-tenant (the
# deployer cannot write to the sign-in tenant): set false and supply entra_client_id from an app
# you register in that tenant separately (see docs/deploy/runbook.md).
variable "create_entra_app" {
  type        = bool
  description = "Whether Terraform creates the Entra app in entra_tenant_id (false = supply it externally)."
  default     = true
}

variable "entra_client_id" {
  type        = string
  description = "Application (client) id of an externally-registered Entra app (when create_entra_app = false)."
  default     = ""
}

# --- Bot surface (Azure Bot Service + Teams channel) ---
# The bot endpoint ships with the backend either way; these resources register it as a Teams bot so
# the court card's buttons work natively in Teams. Cross-tenant note: the Azure Bot resource lives
# in the subscription's tenant while users sign in from the M365 tenant — hence the multi-tenant
# bot app registration.
variable "create_bot" {
  type        = bool
  description = "Whether to register the Azure Bot resource + Teams channel for the approval-card surface."
  default     = false
}

variable "create_bot_app" {
  type        = bool
  description = "Whether Terraform creates the bot's multi-tenant app registration (false = supply bot_app_id/bot_app_password externally)."
  default     = true
}

variable "bot_app_id" {
  type        = string
  description = "Application (client) id of an externally-registered bot app (when create_bot_app = false)."
  default     = ""
}

variable "bot_app_password" {
  type        = string
  description = "Client secret of an externally-registered bot app (when create_bot_app = false). Stored as a Container App secret."
  default     = ""
  sensitive   = true
}
