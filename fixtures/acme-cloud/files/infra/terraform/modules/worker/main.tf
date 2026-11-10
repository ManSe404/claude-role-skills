variable "name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "environment_id" {
  type = string
}

variable "image" {
  type = string
}

variable "queue_namespace" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

resource "azurerm_container_app" "worker" {
  name                         = var.name
  location                     = var.location
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.environment_id
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type = "SystemAssigned"
  }

  template {
    min_replicas = 1
    max_replicas = 4

    container {
      name   = "worker"
      image  = var.image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "SERVICEBUS_NAMESPACE"
        value = var.queue_namespace
      }
    }
  }
}

output "principal_id" {
  value = azurerm_container_app.worker.identity[0].principal_id
}
