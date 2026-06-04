# Entra ID application backing the MCP resource server. The backend validates access tokens whose
# audience is this app's Application ID URI (api://<client-id>) and whose issuer is the tenant's
# v2.0 endpoint — exactly what main.tf passes as OAUTH_AUDIENCE / OAUTH_ISSUER.
#
# Created here only when create_entra_app = true (same-tenant deployments). In a cross-tenant setup
# — where the deployer's identity cannot write to the sign-in tenant — set create_entra_app = false
# and supply entra_client_id from an app registered in that tenant separately.

resource "random_uuid" "court_use_scope" {
  count = var.create_entra_app ? 1 : 0
}

resource "azuread_application" "court" {
  count            = var.create_entra_app ? 1 : 0
  display_name     = var.app_display_name
  sign_in_audience = "AzureADMyOrg"

  api {
    # Access tokens are v2.0, so the issuer is https://login.microsoftonline.com/<tenant>/v2.0.
    requested_access_token_version = 2

    oauth2_permission_scope {
      id                         = random_uuid.court_use_scope[0].result
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
  count          = var.create_entra_app ? 1 : 0
  application_id = azuread_application.court[0].id
  identifier_uri = "api://${azuread_application.court[0].client_id}"
}

resource "azuread_service_principal" "court" {
  count     = var.create_entra_app ? 1 : 0
  client_id = azuread_application.court[0].client_id
}

# Client secret for the Teams OAuth connection registration (set OAUTH_CONNECTION_ID after that step).
resource "azuread_application_password" "court" {
  count          = var.create_entra_app ? 1 : 0
  application_id = azuread_application.court[0].id
  display_name   = "teams-oauth-connection"
  end_date       = "2027-06-30T00:00:00Z"
}

locals {
  # The client id the backend validates tokens against — the created app, or the externally
  # supplied one in a cross-tenant deployment.
  entra_client_id = var.create_entra_app ? azuread_application.court[0].client_id : var.entra_client_id
}
