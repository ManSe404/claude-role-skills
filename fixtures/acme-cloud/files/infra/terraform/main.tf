# Resource groups, one per concern, in the one subscription we have.

resource "azurerm_resource_group" "app" {
  name     = "rg-${local.prefix}-app"
  location = var.location
  tags     = local.tags
}

resource "azurerm_resource_group" "data" {
  name     = "rg-${local.prefix}-data"
  location = var.location
  tags     = local.tags
}

resource "azurerm_resource_group" "network" {
  name     = "rg-${local.prefix}-network"
  location = var.location
  tags     = local.tags
}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

data "azurerm_dns_zone" "public" {
  name                = "tickets.example.com"
  resource_group_name = "rg-acme-shared-dns"
}

resource "azurerm_dns_cname_record" "portal" {
  name                = "www"
  zone_name           = data.azurerm_dns_zone.public.name
  resource_group_name = data.azurerm_dns_zone.public.resource_group_name
  ttl                 = 300
  record              = azurerm_linux_web_app.portal.default_hostname
}
