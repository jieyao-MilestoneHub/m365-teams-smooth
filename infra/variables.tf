variable "subscription_id" {
  type        = string
  description = "Azure subscription to deploy into."
}

variable "tenant_id" {
  type        = string
  description = "Entra ID (Microsoft 365) tenant id. Also forms the OAuth issuer/JWKS URLs."
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
