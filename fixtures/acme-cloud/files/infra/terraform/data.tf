resource "azurerm_mssql_server" "main" {
  name                         = "sql-${local.prefix}"
  resource_group_name          = azurerm_resource_group.data.name
  location                     = var.location
  version                      = "12.0"
  administrator_login          = "acmesqladmin"
  administrator_login_password = var.sql_admin_password
  minimum_tls_version          = "1.2"
  tags                         = local.tags
}

resource "azurerm_mssql_database" "tickets" {
  name           = "db-tickets"
  server_id      = azurerm_mssql_server.main.id
  sku_name       = "GP_Gen5_2"
  max_size_gb    = 100
  zone_redundant = false
  tags           = local.tags
}

resource "azurerm_mssql_firewall_rule" "allow_all" {
  name             = "allow-all-temporary"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "255.255.255.255"
}

resource "azurerm_storage_account" "tickets" {
  name                            = "stacmetickets${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.data.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "ZRS"
  min_tls_version                 = "TLS1_2"
  public_network_access_enabled   = false
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_storage_account" "backups" {
  name                            = "stacmebackupsprod"
  resource_group_name             = azurerm_resource_group.data.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "GRS"
  min_tls_version                 = "TLS1_2"
  public_network_access_enabled   = false
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_key_vault" "main" {
  name                          = "kv-${local.prefix}"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.data.name
  tenant_id                     = var.tenant_id
  sku_name                      = "standard"
  purge_protection_enabled      = true
  rbac_authorization_enabled    = true
  public_network_access_enabled = false
  tags                          = local.tags
}

resource "azurerm_private_endpoint" "vault" {
  name                = "pe-${local.prefix}-vault"
  location            = var.location
  resource_group_name = azurerm_resource_group.network.name
  subnet_id           = azurerm_subnet.data.id

  private_service_connection {
    name                           = "vault"
    private_connection_resource_id = azurerm_key_vault.main.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }
}

resource "azurerm_private_endpoint" "tickets" {
  name                = "pe-${local.prefix}-tickets"
  location            = var.location
  resource_group_name = azurerm_resource_group.network.name
  subnet_id           = azurerm_subnet.data.id

  private_service_connection {
    name                           = "tickets"
    private_connection_resource_id = azurerm_storage_account.tickets.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }
}
