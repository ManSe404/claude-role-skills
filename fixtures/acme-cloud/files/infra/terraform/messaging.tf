resource "azurerm_servicebus_namespace" "main" {
  name                = "sb-${local.prefix}"
  location            = var.location
  resource_group_name = azurerm_resource_group.app.name
  sku                 = "Standard"
  minimum_tls_version = "1.2"
  local_auth_enabled  = false
  tags                = local.tags
}

resource "azurerm_servicebus_queue" "queues" {
  for_each     = toset(["ticket-emails", "seat-holds"])
  name         = each.value
  namespace_id = azurerm_servicebus_namespace.main.id
}
