resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.prefix}"
  location            = var.location
  resource_group_name = azurerm_resource_group.app.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_application_insights" "portal" {
  name                = "appi-${local.prefix}-portal"
  location            = var.location
  resource_group_name = azurerm_resource_group.app.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.tags
}

resource "azurerm_monitor_diagnostic_setting" "portal" {
  name                       = "to-log-analytics"
  target_resource_id         = azurerm_linux_web_app.portal.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category_group = "allLogs"
  }
}

resource "azurerm_monitor_diagnostic_setting" "vault" {
  name                       = "to-log-analytics"
  target_resource_id         = azurerm_key_vault.main.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category_group = "audit"
  }
}

resource "azurerm_monitor_diagnostic_setting" "servicebus" {
  name                       = "to-log-analytics"
  target_resource_id         = azurerm_servicebus_namespace.main.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category_group = "allLogs"
  }
}
