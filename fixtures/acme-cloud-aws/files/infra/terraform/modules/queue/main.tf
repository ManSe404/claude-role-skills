variable "name" {
  type = string
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-dlq"
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "main" {
  name = var.name

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })
}

output "arn" {
  value = aws_sqs_queue.main.arn
}

output "url" {
  value = aws_sqs_queue.main.url
}
