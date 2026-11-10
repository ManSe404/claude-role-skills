resource "azurerm_virtual_network" "main" {
  name                = "vnet-${local.prefix}"
  location            = var.location
  resource_group_name = azurerm_resource_group.network.name
  address_space       = ["10.20.0.0/16"]
  tags                = local.tags
}

resource "azurerm_subnet" "app" {
  name                 = "snet-app"
  resource_group_name  = azurerm_resource_group.network.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.20.1.0/24"]

  delegation {
    name = "web"

    service_delegation {
      name = "Microsoft.Web/serverFarms"
    }
  }
}

resource "azurerm_subnet" "jobs" {
  name                 = "snet-jobs"
  resource_group_name  = azurerm_resource_group.network.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.20.2.0/23"]
}

resource "azurerm_subnet" "data" {
  name                 = "snet-data"
  resource_group_name  = azurerm_resource_group.network.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.20.4.0/24"]
}

resource "azurerm_network_security_group" "jobs" {
  name                = "nsg-${local.prefix}-jobs"
  location            = var.location
  resource_group_name = azurerm_resource_group.network.name

  security_rule {
    name                       = "allow-https-from-lb"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-ssh-admin"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "jobs" {
  subnet_id                 = azurerm_subnet.jobs.id
  network_security_group_id = azurerm_network_security_group.jobs.id
}
