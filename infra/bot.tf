# Azure Bot Service registration for the approval-card surface. The bot itself is the backend
# process (POST /api/messages on the Container App); this resource is the channel registration that
# lets Microsoft Teams deliver activities there and render the court card's native buttons.
#
# The bot's app registration is separate from the court app on purpose: the court app is the MCP
# resource server (single-tenant, audience api://<id>), while the bot's identity authenticates the
# Bot Framework channel and must be multi-tenant when the Azure subscription and the sign-in
# tenant differ. Created only when create_bot_app = true; in a cross-tenant setup where the
# deployer cannot write app registrations, set it false and supply bot_app_id / bot_app_password
# from an app registered separately.

resource "azuread_application" "bot" {
  count            = var.create_bot && var.create_bot_app ? 1 : 0
  display_name     = "${var.app_display_name} Bot"
  sign_in_audience = "AzureADMultipleOrgs"
}

resource "azuread_service_principal" "bot" {
  count     = var.create_bot && var.create_bot_app ? 1 : 0
  client_id = azuread_application.bot[0].client_id
}

resource "azuread_application_password" "bot" {
  count          = var.create_bot && var.create_bot_app ? 1 : 0
  application_id = azuread_application.bot[0].id
  display_name   = "bot-framework-auth"
  end_date       = "2027-06-30T00:00:00Z"
}

locals {
  bot_app_id       = var.create_bot ? (var.create_bot_app ? azuread_application.bot[0].client_id : var.bot_app_id) : ""
  bot_app_password = var.create_bot ? (var.create_bot_app ? azuread_application_password.bot[0].value : var.bot_app_password) : ""
}

resource "azurerm_bot_service_azure_bot" "this" {
  count               = var.create_bot ? 1 : 0
  name                = "${var.name}-bot"
  resource_group_name = azurerm_resource_group.this.name
  location            = "global"
  sku                 = "F0"

  microsoft_app_id   = local.bot_app_id
  microsoft_app_type = "MultiTenant"

  # Activities land on the backend's Bot Framework endpoint.
  endpoint = "${local.public_base_url}/api/messages"
}

resource "azurerm_bot_channel_ms_teams" "this" {
  count               = var.create_bot ? 1 : 0
  bot_name            = azurerm_bot_service_azure_bot.this[0].name
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_bot_service_azure_bot.this[0].location
}
