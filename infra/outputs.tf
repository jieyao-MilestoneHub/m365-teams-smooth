# --- Backend hosting ---

output "acr_login_server" {
  description = "Registry to docker push the backend image to."
  value       = azurerm_container_registry.this.login_server
}

output "image_reference" {
  description = "Full image reference the Container App runs (build/push this tag)."
  value       = "${azurerm_container_registry.this.login_server}/${var.image_repository}:${var.image_tag}"
}

output "public_base_url" {
  description = "PUBLIC_BASE_URL — the backend's public origin. The MCP endpoint is this + /mcp."
  value       = local.public_base_url
}

# --- M365 app packaging placeholders (feed m365/package.py) ---

output "mcp_server_url" {
  description = "MCP_SERVER_URL placeholder for m365/ai-plugin.json."
  value       = "${local.public_base_url}/mcp"
}

output "mcp_host_domain" {
  description = "MCP_HOST_DOMAIN placeholder for m365/manifest.json."
  value       = local.app_fqdn
}

# --- OAuth / Entra ID ---

output "entra_client_id" {
  description = "Application (client) id of the Entra app."
  value       = local.entra_client_id
}

output "oauth_audience" {
  description = "OAUTH_AUDIENCE — the API's Application ID URI."
  value       = "api://${local.entra_client_id}"
}

output "oauth_issuer" {
  description = "OAUTH_ISSUER for the backend."
  value       = "https://login.microsoftonline.com/${var.entra_tenant_id}/v2.0"
}

output "oauth_jwks_url" {
  description = "OAUTH_JWKS_URL for the backend."
  value       = "https://login.microsoftonline.com/${var.entra_tenant_id}/discovery/v2.0/keys"
}

output "court_scope" {
  description = "The delegated scope the agent requests (api://<client-id>/court.use)."
  value       = "api://${local.entra_client_id}/court.use"
}

output "entra_client_secret" {
  description = "Client secret for the Teams OAuth connection (only when Terraform created the app)."
  value       = var.create_entra_app ? azuread_application_password.court[0].value : ""
  sensitive   = true
}
