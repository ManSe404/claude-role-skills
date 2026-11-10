module "orders_queue" {
  source = "./modules/queue"
  name   = "${local.prefix}-orders"
}
