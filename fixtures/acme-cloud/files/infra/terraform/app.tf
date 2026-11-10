resource "azurerm_service_plan" "main" {
  name                   = "plan-${local.prefix}"
  location               = var.location
  resource_group_name    = azurerm_resource_group.app.name
  os_type                = "Linux"
  sku_name               = "P1v3"
  worker_count           = 1
  zone_balancing_enabled = false
  tags                   = local.tags
}

resource "azurerm_linux_web_app" "portal" {
  name                      = "app-${local.prefix}-portal"
  location                  = var.location
  resource_group_name       = azurerm_resource_group.app.name
  service_plan_id           = azurerm_service_plan.main.id
  https_only                = true
  virtual_network_subnet_id = azurerm_subnet.app.id

  site_config {
    minimum_tls_version = "1.2"

    application_stack {
      dotnet_version = "8.0"
    }
  }

  app_settings = {
    "ASPNETCORE_ENVIRONMENT" = "Production"
    "SQL_SERVER"             = azurerm_mssql_server.main.fully_qualified_domain_name
    "TICKET_STORAGE"         = azurerm_storage_account.tickets.primary_blob_endpoint
    "SERVICEBUS_NAMESPACE"   = azurerm_servicebus_namespace.main.name
    "KEY_VAULT_URL"          = azurerm_key_vault.main.vault_uri
    "SMTP_PASSWORD"          = "fake-smtp-password-not-real-7Qw"
  }

  tags = local.tags
}

resource "azurerm_container_app_environment" "jobs" {
  name                           = "cae-${local.prefix}"
  location                       = var.location
  resource_group_name            = azurerm_resource_group.app.name
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.main.id
  infrastructure_subnet_id       = azurerm_subnet.jobs.id
  internal_load_balancer_enabled = true
  tags                           = local.tags
}

module "worker" {
  source = "./modules/worker"

  name                = "ca-${local.prefix}-worker"
  location            = var.location
  resource_group_name = azurerm_resource_group.app.name
  environment_id      = azurerm_container_app_environment.jobs.id
  image               = "${var.container_registry}/tickets-worker:1.8.2"
  queue_namespace     = azurerm_servicebus_namespace.main.name
  tags                = local.tags
}
