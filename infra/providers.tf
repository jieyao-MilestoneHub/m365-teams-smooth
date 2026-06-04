terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# Runtime resources deploy into the Azure subscription's tenant; the app registration lives in the
# Entra ID (M365) tenant users sign in to. The two often differ in enterprise topologies.
provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  tenant_id       = var.azure_tenant_id
}

provider "azuread" {
  tenant_id = var.entra_tenant_id
}
