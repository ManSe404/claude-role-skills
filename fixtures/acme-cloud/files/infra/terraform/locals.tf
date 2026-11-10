locals {
  prefix = "acme-tickets-${var.environment}"

  tags = {
    product = "tickets"
    owner   = "platform@example.com"
  }
}
