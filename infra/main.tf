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

# Keyless data-plane access for knowledge grounding: the backend reaches Azure AI Search (and the
# OpenAI account answering for the knowledge base) with DefaultAzureCredential via the app identity.
resource "azurerm_role_assignment" "knowledge_search_reader" {
  count                = var.knowledge_search_resource_id == "" ? 0 : 1
  scope                = var.knowledge_search_resource_id
  role_definition_name = "Search Index Data Reader"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "knowledge_openai_user" {
  count                = var.knowledge_openai_resource_id == "" ? 0 : 1
  scope                = var.knowledge_openai_resource_id
  role_definition_name = "Cognitive Services OpenAI User"
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

  dynamic "secret" {
    for_each = var.graph_client_secret == "" ? [] : [1]
    content {
      name  = "graph-client-secret"
      value = var.graph_client_secret
    }
  }

  dynamic "secret" {
    for_each = var.llm_api_key == "" ? [] : [1]
    content {
      name  = "llm-api-key"
      value = var.llm_api_key
    }
  }

  dynamic "secret" {
    for_each = local.bot_app_password == "" ? [] : [1]
    content {
      name  = "bot-app-password"
      value = local.bot_app_password
    }
  }

  dynamic "secret" {
    for_each = var.run_link_secret == "" ? [] : [1]
    content {
      name  = "run-link-secret"
      value = var.run_link_secret
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
        value = tostring(var.dry_run_default)
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
        value = "https://login.microsoftonline.com/${var.entra_tenant_id}/v2.0"
      }
      env {
        name  = "OAUTH_JWKS_URL"
        value = "https://login.microsoftonline.com/${var.entra_tenant_id}/discovery/v2.0/keys"
      }
      env {
        name  = "OAUTH_AUDIENCE"
        value = "api://${local.entra_client_id}"
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

      # Read-only run page: cards mint signed deep links only when this secret is present.
      dynamic "env" {
        for_each = var.run_link_secret == "" ? [] : [1]
        content {
          name        = "RUN_LINK_SECRET"
          secret_name = "run-link-secret"
        }
      }

      # Microsoft Graph read-only evidence. The non-secret identifiers go in plain env; the client
      # secret rides a Container App secret. All three of tenant/client/secret must be present for the
      # backend's graph-ready gate to offer the real Outlook/SharePoint adapters — otherwise it mocks.
      env {
        name  = "GRAPH_TENANT_ID"
        value = var.graph_tenant_id
      }
      env {
        name  = "GRAPH_CLIENT_ID"
        value = var.graph_client_id
      }
      dynamic "env" {
        for_each = var.graph_client_secret == "" ? [] : [1]
        content {
          name        = "GRAPH_CLIENT_SECRET"
          secret_name = "graph-client-secret"
        }
      }
      env {
        name  = "OUTLOOK_CALENDAR_UPN"
        value = var.outlook_calendar_upn
      }
      env {
        name  = "SHAREPOINT_SITE_ID"
        value = var.sharepoint_site_id
      }

      # Every keyless dependency (Azure OpenAI, AI Search) authenticates as the user-assigned
      # identity; DefaultAzureCredential needs its client id explicitly, so it is always injected.
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.app.client_id
      }

      # Knowledge grounding (Azure AI Search agentic retrieval). Injected only when configured so
      # the backend's provider selection stays on its offline fallback otherwise.
      dynamic "env" {
        for_each = var.knowledge_search_endpoint == "" ? [] : [1]
        content {
          name  = "KNOWLEDGE_SEARCH_ENDPOINT"
          value = var.knowledge_search_endpoint
        }
      }
      dynamic "env" {
        for_each = var.knowledge_base_name == "" ? [] : [1]
        content {
          name  = "KNOWLEDGE_BASE_NAME"
          value = var.knowledge_base_name
        }
      }
      dynamic "env" {
        for_each = var.knowledge_source_name == "" ? [] : [1]
        content {
          name  = "KNOWLEDGE_SOURCE_NAME"
          value = var.knowledge_source_name
        }
      }

      # Agentic roles (Prosecutor read-selection, Defender planning). Injected only when an Azure
      # OpenAI endpoint is set; with force_all_mock = false this turns the roles agentic, otherwise
      # they stay deterministic. LLM_API_KEY is optional — omit it for keyless (managed identity).
      dynamic "env" {
        for_each = var.azure_openai_endpoint == "" ? [] : [1]
        content {
          name  = "AZURE_OPENAI_ENDPOINT"
          value = var.azure_openai_endpoint
        }
      }
      dynamic "env" {
        for_each = var.azure_openai_deployment == "" ? [] : [1]
        content {
          name  = "AZURE_OPENAI_DEPLOYMENT"
          value = var.azure_openai_deployment
        }
      }
      dynamic "env" {
        for_each = var.azure_openai_deployment_fast == "" ? [] : [1]
        content {
          name  = "AZURE_OPENAI_DEPLOYMENT_FAST"
          value = var.azure_openai_deployment_fast
        }
      }
      dynamic "env" {
        for_each = var.llm_api_key == "" ? [] : [1]
        content {
          name        = "LLM_API_KEY"
          secret_name = "llm-api-key"
        }
      }

      # Separation of duties: role → approver identity map. Empty leaves the legacy single-verdict
      # flow; set it to enforce the two-gate approval workflow.
      dynamic "env" {
        for_each = var.approver_directory == "" ? [] : [1]
        content {
          name  = "APPROVER_DIRECTORY"
          value = var.approver_directory
        }
      }

      # Approval notifications (Microsoft Graph activity feed). Best-effort and never blocks a trial;
      # injected only when a channel is selected so an unset deployment simply sends nothing.
      dynamic "env" {
        for_each = var.notify_mode == "" ? [] : [1]
        content {
          name  = "NOTIFY_MODE"
          value = var.notify_mode
        }
      }
      dynamic "env" {
        for_each = var.notify_teams_app_id == "" ? [] : [1]
        content {
          name  = "NOTIFY_TEAMS_APP_ID"
          value = var.notify_teams_app_id
        }
      }
      dynamic "env" {
        for_each = var.notify_link_url == "" ? [] : [1]
        content {
          name  = "NOTIFY_LINK_URL"
          value = var.notify_link_url
        }
      }

      # Bot surface (Azure Bot Service). Empty BOT_APP_ID leaves the endpoint in anonymous mode
      # (local Playground); these wire it to the registered bot so Teams can authenticate.
      dynamic "env" {
        for_each = local.bot_app_id == "" ? [] : [1]
        content {
          name  = "BOT_APP_ID"
          value = local.bot_app_id
        }
      }
      dynamic "env" {
        for_each = local.bot_app_password == "" ? [] : [1]
        content {
          name        = "BOT_APP_PASSWORD"
          secret_name = "bot-app-password"
        }
      }
      dynamic "env" {
        for_each = local.bot_app_id == "" ? [] : [1]
        content {
          name  = "BOT_APP_TYPE"
          value = "MultiTenant"
        }
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull]
}
