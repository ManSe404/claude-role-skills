variable "subscription_id" {
  description = "The Acme Tickets production subscription."
  type        = string
  default     = "00000000-0000-0000-0000-000000000000"
}

variable "tenant_id" {
  description = "The directory the Key Vault trusts."
  type        = string
  default     = "00000000-0000-0000-0000-000000000000"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "location" {
  type    = string
  default = "westeurope"
}

variable "sql_admin_password" {
  description = "Set from the pipeline, never in code."
  type        = string
  sensitive   = true
}

variable "container_registry" {
  type    = string
  default = "acrticketsprod.azurecr.io"
}
