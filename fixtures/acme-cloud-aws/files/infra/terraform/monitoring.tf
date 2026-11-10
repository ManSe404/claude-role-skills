resource "aws_cloudwatch_log_group" "portal" {
  name              = "/ecs/${local.prefix}-portal"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "worker" {
  name = "/ecs/${local.prefix}-worker"
}
