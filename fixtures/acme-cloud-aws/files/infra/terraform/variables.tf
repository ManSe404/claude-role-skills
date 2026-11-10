variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "certificate_arn" {
  type        = string
  description = "ACM certificate for the portal, created by hand"
}
