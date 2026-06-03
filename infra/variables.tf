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

variable "app_display_name" {
  type        = string
  description = "Display name for the Entra ID app registration."
  default     = "AI Change Court"
}
