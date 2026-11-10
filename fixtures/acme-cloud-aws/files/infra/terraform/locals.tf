locals {
  prefix = "stagefront-${var.environment}"

  tags = {
    product = "tickets"
    env     = var.environment
  }
}
