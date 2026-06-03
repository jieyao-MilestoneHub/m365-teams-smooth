# Entra ID application backing the MCP resource server. The backend validates access tokens whose
# audience is this app's Application ID URI (api://<client-id>) and whose issuer is the tenant's
# v2.0 endpoint — exactly what main.tf passes as OAUTH_AUDIENCE / OAUTH_ISSUER.

resource "random_uuid" "court_use_scope" {}

resource "azuread_application" "court" {
  display_name     = var.app_display_name
  sign_in_audience = "AzureADMyOrg"

  api {
    # Access tokens are v2.0, so the issuer is https://login.microsoftonline.com/<tenant>/v2.0.
    requested_access_token_version = 2

    oauth2_permission_scope {
      id                         = random_uuid.court_use_scope.result
      value                      = "court.use"
      type                       = "User"
      enabled                    = true
      admin_consent_display_name = "Use the AI Change Court"
      admin_consent_description  = "Allows the agent to open, review, and resume Change Court trials."
      user_consent_display_name  = "Use the AI Change Court"
      user_consent_description   = "Allows the agent to open, review, and resume Change Court trials."
    }
  }

  # The Teams token service redirects here when brokering the OAuth connection used by the plugin.
  web {
    redirect_uris = ["https://token.botframework.com/.auth/web/redirect"]
  }
}

# Application ID URI (api://<client-id>) as a separate resource to avoid a self-reference cycle.
resource "azuread_application_identifier_uri" "court" {
  application_id = azuread_application.court.id
  identifier_uri = "api://${azuread_application.court.client_id}"
}

resource "azuread_service_principal" "court" {
  client_id = azuread_application.court.client_id
}

# Client secret for the Teams OAuth connection registration (set OAUTH_CONNECTION_ID after that step).
resource "azuread_application_password" "court" {
  application_id = azuread_application.court.id
  display_name   = "teams-oauth-connection"
  end_date       = "2027-06-30T00:00:00Z"
}
