resource "azurerm_resource_group" "this" {
  name     = "${var.name}-rg"
  location = var.location
}

# Private registry the Container App pulls from. Basic is the cheapest SKU.
resource "azurerm_container_registry" "this" {
  name                = replace("${var.name}acr", "-", "")
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "Basic"
  admin_enabled       = false
}

# User-assigned identity the Container App uses to pull from ACR. Using a UAMI (rather than the
# app's system identity) avoids a create-time cycle between the role assignment and the app.
resource "azurerm_user_assigned_identity" "app" {
  name                = "${var.name}-id"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.this.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "${var.name}-logs"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "this" {
  name                       = "${var.name}-env"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = azurerm_resource_group.this.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
}

locals {
  # Container Apps ingress FQDN is "<app-name>.<environment-default-domain>" — known from the
  # environment before the app exists, so PUBLIC_BASE_URL has no dependency cycle.
  app_fqdn        = "${var.name}.${azurerm_container_app_environment.this.default_domain}"
  public_base_url = "https://${local.app_fqdn}"
}

resource "azurerm_container_app" "this" {
  name                         = var.name
  resource_group_name          = azurerm_resource_group.this.name
  container_app_environment_id = azurerm_container_app_environment.this.id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  dynamic "secret" {
    for_each = var.github_token == "" ? [] : [1]
    content {
      name  = "github-token"
      value = var.github_token
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = 1

    container {
      name   = "backend"
      image  = "${azurerm_container_registry.this.login_server}/${var.image_repository}:${var.image_tag}"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "FORCE_ALL_MOCK"
        value = tostring(var.force_all_mock)
      }
      env {
        name  = "DRY_RUN_DEFAULT"
        value = "true"
      }
      env {
        name  = "INTEGRATION_MODE"
        value = var.integration_mode
      }
      env {
        name  = "PUBLIC_BASE_URL"
        value = local.public_base_url
      }
      env {
        name  = "OAUTH_ISSUER"
        value = "https://login.microsoftonline.com/${var.tenant_id}/v2.0"
      }
      env {
        name  = "OAUTH_JWKS_URL"
        value = "https://login.microsoftonline.com/${var.tenant_id}/discovery/v2.0/keys"
      }
      env {
        name  = "OAUTH_AUDIENCE"
        value = "api://${azuread_application.court.client_id}"
      }
      env {
        name  = "GITHUB_REPO"
        value = var.github_repo
      }

      dynamic "env" {
        for_each = var.github_token == "" ? [] : [1]
        content {
          name        = "GITHUB_TOKEN"
          secret_name = "github-token"
        }
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull]
}
