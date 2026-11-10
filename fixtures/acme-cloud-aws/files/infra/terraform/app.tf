resource "aws_lb" "web" {
  name               = "${local.prefix}-web"
  load_balancer_type = "application"
  internal           = false
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]
  security_groups    = [aws_security_group.alb.id]
  tags               = local.tags
}

resource "aws_lb_target_group" "portal" {
  name        = "${local.prefix}-portal"
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.web.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.portal.arn
  }
}

resource "aws_ecs_cluster" "main" {
  name = "${local.prefix}-apps"
  tags = local.tags
}

resource "aws_ecs_task_definition" "portal" {
  family                   = "${local.prefix}-portal"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name  = "portal"
      image = "000000000000.dkr.ecr.eu-central-1.amazonaws.com/stagefront-portal:2.6.1"
      portMappings = [
        { containerPort = 8080 }
      ]
      environment = [
        { name = "DB_HOST", value = aws_db_instance.main.address },
        { name = "SMTP_HOST", value = "mail.example.com" },
        { name = "SMTP_PASSWORD", value = "fake-smtp-password-not-real-9Kd" },
      ]
      secrets = [
        { name = "DB_PASSWORD", valueFrom = aws_secretsmanager_secret.db.arn }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.portal.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "portal"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "portal" {
  name            = "${local.prefix}-portal"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.portal.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.portal.arn
    container_name   = "portal"
    container_port   = 8080
  }
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name  = "worker"
      image = "000000000000.dkr.ecr.eu-central-1.amazonaws.com/stagefront-worker:latest"
      environment = [
        { name = "QUEUE_URL", value = module.orders_queue.url },
        { name = "DB_HOST", value = aws_db_instance.main.address },
      ]
      secrets = [
        { name = "DB_PASSWORD", valueFrom = aws_secretsmanager_secret.db.arn }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "worker" {
  name            = "${local.prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_groups = [aws_security_group.app.id]
  }
}
